"""
Workflow management and execution system.
Handles workflow validation, execution, and state management.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import subprocess
import sys

from PySide6.QtCore import QObject, Signal, QTimer

from utils.logging_utils import get_logger


class WorkflowManager(QObject):
    """Manages workflow execution and state."""
    
    # Signals
    workflow_started = Signal()
    workflow_finished = Signal(bool, str)  # success, message
    workflow_paused = Signal()
    workflow_resumed = Signal()
    # User input specific pause/resume (separate from global workflow pause)
    user_input_paused = Signal(str, str)  # node_id, message
    user_input_resumed = Signal(str)  # node_id
    node_started = Signal(str)  # node_id
    node_finished = Signal(str, bool, str)  # node_id, success, message
    progress_updated = Signal(int)  # overall workflow percentage
    # Per-node UI updates
    node_progress_updated = Signal(str, int, str)  # node_id, percent (-1 indeterminate), message
    node_log_appended = Signal(str, str)  # node_id, line
    node_error_reported = Signal(str, str)  # node_id, error_message
    # Pause hint (UI-thread) to show a yellow pause panel on the node
    node_pause_hint = Signal(str, str)  # node_id, message
    # UI thread delivery of node results: node_id, result dict, inputs dict
    node_result_emitted = Signal(str, object, object)
    # Ensure visual updates occur on the GUI thread
    node_state_update = Signal(str, str)  # node_id, state
    # Validation animation completion (UI hint)
    validation_animation_finished = Signal()
    
    def __init__(self):
        super().__init__()
        
        self.logger = get_logger(__name__)
        
        # Workflow state
        self.nodes = {}
        self.connections = {}
        self.execution_order = []
        self.is_running = False
        self.is_paused = False
        self.user_input_paused_nodes = set()  # Track nodes waiting for user input
        self.current_workflow_file = None
        
        # Execution state
        self.executed_nodes = set()
        self.node_results = {}
        self._pause_event = threading.Event()
        self._stop_event = threading.Event()
        self._current_thread = None

        # Thread-safety and per-run snapshots
        self._state_lock = threading.RLock()
        self._run_nodes: Dict[str, Dict[str, Any]] = {}
        self._run_connections: Dict[str, Dict[str, Any]] = {}
        # External process tracking for hard-stop support
        self._active_processes: dict[str, list[subprocess.Popen]] = {}
        self._active_process_lock = threading.RLock()
        self._user_stopped: bool = False

        # Live canvas integration (optional)
        self._live_canvas = None
        self._node_live_map: dict[str, object] = {}

        # Route node results back to UI thread for inline viewers
        self.node_result_emitted.connect(self._on_node_result)
        # Route visual state changes to UI thread
        self.node_state_update.connect(self._update_node_visual_state)
        # Per-node progress and error to UI thread
        self.node_progress_updated.connect(self._on_node_progress)
        self.node_error_reported.connect(self._on_node_error)
        # Live log streaming
        self.node_log_appended.connect(self._on_node_log)
        # Pause hint routed to GUI thread
        self.node_pause_hint.connect(self._on_node_pause_hint)

        # Validation preview animation (UI-thread)
        self._validate_anim_timer: QTimer | None = None
        self._validate_anim_index: int = -1
        self._validate_anim_order: list[str] = []
        try:
            self._validate_anim_timer = QTimer(self)
            self._validate_anim_timer.timeout.connect(self._on_validate_anim_tick)
            self._validate_anim_timer.setInterval(120)
        except Exception:
            self._validate_anim_timer = None

    def _sanitize_graph(self) -> None:
        """Remove invalid/dangling connections and ports under lock.

        - Drops connections whose source/target nodes are missing
        - Drops connections whose port names don't exist on the node snapshot
        - Deduplicates identical connections (same src/dst/ports)
        """
        try:
            with self._state_lock:
                nodes = dict(self.nodes)
                conns_in = dict(self.connections)
            valid_nodes = set(nodes.keys())
            seen: set[tuple[str, str, str, str]] = set()
            sanitized: Dict[str, Dict[str, Any]] = {}
            removed = 0
            for cid, c in conns_in.items():
                try:
                    src = str(c.get('source_node'))
                    dst = str(c.get('target_node'))
                    sp = str(c.get('source_port'))
                    tp = str(c.get('target_port'))
                except Exception:
                    removed += 1
                    continue
                # Node existence
                if src not in valid_nodes or dst not in valid_nodes:
                    removed += 1
                    continue
                # Port existence (best-effort using captured lists)
                src_ports = set(nodes[src].get('outputs') or [])
                dst_ports = set(nodes[dst].get('inputs') or [])
                if (sp and src_ports) and sp not in src_ports:
                    removed += 1
                    continue
                if (tp and dst_ports) and tp not in dst_ports:
                    removed += 1
                    continue
                key = (src, sp, dst, tp)
                if key in seen:
                    # duplicate
                    removed += 1
                    continue
                seen.add(key)
                sanitized[cid] = c
            if removed:
                self.logger.info(f"Sanitized workflow graph: removed {removed} invalid connections")
            with self._state_lock:
                self.connections = sanitized
        except Exception as e:
            try:
                self.logger.warning(f"Sanitize graph failed: {e}")
            except Exception:
                pass

    def bind_canvas(self, canvas) -> None:
        """Bind a live canvas for optional UI updates during execution."""
        self._live_canvas = canvas
        
    def update_workflow(self):
        """Legacy no-arg update hook (kept for compatibility)."""
        #self.logger.info("Workflow updated (no-arg handler)")
        pass

    def update_from_canvas(self, canvas) -> None:
        """Rebuild backend workflow state from the given canvas scene.

        Extracts nodes and connections with their properties and port names.
        """
        try:
            nodes_state: Dict[str, Dict[str, Any]] = {}
            connections_state: Dict[str, Dict[str, Any]] = {}

            # Map QGraphics nodes to stable IDs for this session
            def _node_id(n) -> str:
                return f"node_{id(n)}"

            # Capture nodes (and build live map)
            self._node_live_map = {}
            for node in getattr(canvas, "nodes", []):
                node_id = _node_id(node)
                props = getattr(node, "properties", {}) or {}
                # Serialize position for layout persistence
                try:
                    pos = node.pos()
                    position = {"x": float(pos.x()), "y": float(pos.y())}
                except Exception:
                    position = {"x": 0.0, "y": 0.0}
                # Serialize size for layout persistence
                try:
                    width = float(getattr(node, "width", 0.0))
                    height = float(getattr(node, "height", 0.0))
                    size = {"w": max(0.0, width), "h": max(0.0, height)}
                except Exception:
                    size = {"w": 0.0, "h": 0.0}
                nodes_state[node_id] = {
                    "id": node_id,
                    "type": getattr(node, "node_type", "unknown"),
                    "title": getattr(node, "title", ""),
                    "properties": dict(props),
                    "position": position,
                    "size": size,
                    "inputs": list(getattr(node, "input_ports", {}).keys()),
                    "outputs": list(getattr(node, "output_ports", {}).keys()),
                }
                self._node_live_map[node_id] = node

            # Capture connections
            for conn in getattr(canvas, "connections", []):
                cid = f"conn_{id(conn)}"
                try:
                    source_id = _node_id(conn.output_node)
                    target_id = _node_id(conn.input_node)
                    source_port = conn.output_port
                    target_port = conn.input_port
                except Exception:
                    continue
                connections_state[cid] = {
                    "id": cid,
                    "source_node": source_id,
                    "source_port": source_port,
                    "target_node": target_id,
                    "target_port": target_port,
                    "label": conn.label_item.toPlainText() if getattr(conn, "label_item", None) else "",
                }

            # Replace internal state safely
            with self._state_lock:
                self.nodes = nodes_state
                self.connections = connections_state
            #self.logger.info(f"Synced from canvas: {len(self.nodes)} nodes, {len(self.connections)} connections")

        except Exception as e:
            self.logger.error(f"Failed to sync from canvas: {e}")

    # --- UI update slot used after each node execution ---
    def _on_node_result(self, node_id: str, result: dict, inputs: dict) -> None:
        """If running with a live canvas, update the corresponding QGraphics node in-place."""
        try:
            live_node = self._node_live_map.get(node_id)
            if live_node is None:
                return
            # Sync any updated properties from execution back to the live node
            try:
                props = self.nodes.get(node_id, {}).get("properties", {})
                if isinstance(props, dict):
                    for k, v in props.items():
                        try:
                            live_node.set_property(k, v)
                        except Exception:
                            pass
            except Exception:
                pass
            # Store last inputs on the live node for viewer widgets
            if isinstance(inputs, dict):
                for k in ("data", "string", "image", "bytes", "molecules"):
                    if k in inputs:
                        try:
                            live_node.set_property(f"last_input_{k}", inputs[k])
                        except Exception:
                            pass
            # Deliver result hook for inline updates (defer to avoid deep re-entrancy)
            try:
                QTimer.singleShot(0, lambda n=live_node, r=result: n.on_result(r))
            except Exception:
                try:
                    live_node.on_result(result)
                except Exception:
                    pass

            # Proactively propagate this node's outputs to connected downstream live nodes
            # so their inline UIs (e.g., SelectColumns checkboxes) can refresh schemas
            try:
                conns = list(self.connections.values())
                for conn in conns:
                    if conn.get("source_node") != node_id:
                        continue
                    target_id = conn.get("target_node")
                    target_port = conn.get("target_port")
                    source_port = conn.get("source_port")
                    if not target_id or not target_port:
                        continue
                    target_live = self._node_live_map.get(target_id)
                    if target_live is None:
                        continue
                    # Resolve value for this connection based on source port
                    try:
                        value = result
                        if isinstance(result, dict) and source_port in result:
                            value = result[source_port]
                        elif isinstance(result, dict):
                            # Heuristic: pick common data keys
                            for k in ("data", "results", "records", target_port):
                                if k in result:
                                    value = result[k]
                                    break
                        # Store under specific and generic keys
                        target_live.set_property(f"last_input_{target_port}", value)
                        if target_port == "data":
                            target_live.set_property("last_input_data", value)
                        if target_port == "string":
                            target_live.set_property("last_input_string", value)
                        # Also store a unified alias to help nodes retrieve input-only contexts
                        target_live.set_property("last_input_results", value)
                    except Exception:
                        pass
                    # Nudge target node to update its inline UI based on new inputs (defer)
                    try:
                        QTimer.singleShot(0, lambda n=target_live: n.on_result({"live_update": True}))
                    except Exception:
                        try:
                            target_live.on_result({"live_update": True})
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass
    
    def _update_node_visual_state(self, node_id: str, state: str) -> None:
        """Update the visual state of a node on the canvas."""
        try:
            live_node = self._node_live_map.get(node_id)
            if live_node is None:
                return
            
            # Use the BaseNode state constants
            if hasattr(live_node, 'set_execution_state'):
                live_node.set_execution_state(state)
            # Clear any previous error panel when transitioning out of error
            if state in ("idle", "running", "completed") and hasattr(live_node, 'clear_error'):
                try:
                    live_node.clear_error()
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning(f"Failed to update node visual state: {e}")

    def _on_node_progress(self, node_id: str, percent: int, message: str) -> None:
        """UI-thread handler to apply per-node progress updates to the live node."""
        try:
            live_node = self._node_live_map.get(node_id)
            if live_node is None:
                return
            if hasattr(live_node, 'set_progress'):
                try:
                    live_node.set_progress(int(percent), str(message) if message is not None else "")
                except Exception:
                    pass
        except Exception:
            pass

    def _on_node_log(self, node_id: str, line: str) -> None:
        """UI-thread handler to append a log line under the live node."""
        try:
            live_node = self._node_live_map.get(node_id)
            if live_node is None:
                return
            if hasattr(live_node, 'append_log_line'):
                try:
                    live_node.append_log_line(line)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_node_error(self, node_id: str, message: str) -> None:
        """UI-thread handler to show error panel under the live node."""
        try:
            live_node = self._node_live_map.get(node_id)
            if live_node is None:
                return
            if hasattr(live_node, 'show_error'):
                try:
                    live_node.show_error(message)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _on_node_pause_hint(self, node_id: str, message: str) -> None:
        """UI-thread handler to show a yellow pause hint panel under the node."""
        try:
            live_node = self._node_live_map.get(node_id)
            if live_node is None:
                return
            if hasattr(live_node, 'show_pause'):
                try:
                    live_node.show_pause(message)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _reset_all_nodes_to_idle(self) -> None:
        """Reset all nodes to idle state at the start of workflow execution."""
        for node_id in self.nodes.keys():
            self._update_node_visual_state(node_id, "idle")

    def set_workflow_state(self, nodes_state: list[dict], connections_state: list[dict]):
        """Replace internal workflow state from UI-provided snapshot."""
        with self._state_lock:
            self.nodes = {n["id"]: n for n in nodes_state}
            self.connections = {c["id"]: c for c in connections_state}
        self.logger.info(
            f"Workflow state synced: {len(self.nodes)} nodes, {len(self.connections)} connections"
        )
        
    def load_workflow(self, filename: str) -> bool:
        """Load workflow from file."""
        try:
            with open(filename, 'r') as f:
                workflow_data = json.load(f)
            
            # Clear current workflow
            self.clear_workflow()
            
            # Load nodes
            for node_data in workflow_data.get('nodes', []):
                self.nodes[node_data['id']] = node_data
            
            # Load connections
            for conn_data in workflow_data.get('connections', []):
                self.connections[conn_data['id']] = conn_data
            
            self.current_workflow_file = filename
            self.logger.info(f"Loaded workflow from {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load workflow: {e}")
            return False
    
    def save_workflow(self, filename: str = None) -> bool:
        """Save workflow to file."""
        if filename is None:
            filename = self.current_workflow_file
        
        if filename is None:
            self.logger.error("No filename specified for saving workflow")
            return False
        
        try:
            # Build a sanitized payload to avoid non-JSON-serializable data
            def _json_safe(value, depth: int = 0):
                if value is None or isinstance(value, (str, int, float, bool)):
                    return value
                if isinstance(value, (list, tuple)):
                    if depth > 6:
                        return []
                    return [_json_safe(v, depth + 1) for v in value]
                if isinstance(value, dict):
                    if depth > 6:
                        return {}
                    out = {}
                    for k, v in value.items():
                        # Drop heavy/transient keys
                        if isinstance(k, str) and (k.startswith('last_') or k in {'molecules', 'image', 'bytes', 'array', 'table'}):
                            continue
                        out[str(k)] = _json_safe(v, depth + 1)
                    return out
                try:
                    s = str(value)
                except Exception:
                    s = repr(value)
                if len(s) > 2000:
                    s = s[:2000] + '…'
                return s

            nodes_payload = []
            for node in self.nodes.values():
                try:
                    n = dict(node)
                    props = n.get('properties', {}) or {}
                    n['properties'] = _json_safe(props)
                    pos = n.get('position') or {"x": 0.0, "y": 0.0}
                    n['position'] = {
                        'x': float(pos.get('x', 0.0)) if isinstance(pos, dict) else 0.0,
                        'y': float(pos.get('y', 0.0)) if isinstance(pos, dict) else 0.0,
                    }
                    # Normalize size persistence
                    sz = n.get('size') or {}
                    try:
                        w = float(sz.get('w', 0.0)) if isinstance(sz, dict) else 0.0
                        h = float(sz.get('h', 0.0)) if isinstance(sz, dict) else 0.0
                        if w > 0.0 and h > 0.0:
                            n['size'] = {'w': w, 'h': h}
                        elif 'size' in n:
                            # Drop invalid/empty size
                            n.pop('size', None)
                    except Exception:
                        n.pop('size', None)
                    n['id'] = str(n.get('id', ''))
                    n['type'] = str(n.get('type', 'unknown'))
                    n['title'] = str(n.get('title', ''))
                    for key in ('inputs', 'outputs'):
                        iv = n.get(key)
                        n[key] = [str(x) for x in iv] if isinstance(iv, list) else []
                    nodes_payload.append(n)
                except Exception as e:
                    self.logger.warning(f"Skipping node during save due to error: {e}")
                    continue

            connections_payload = []
            for conn in self.connections.values():
                try:
                    c = dict(conn)
                    for k in ('id', 'source_node', 'source_port', 'target_node', 'target_port'):
                        if k in c:
                            c[k] = str(c[k])
                    if 'label' in c and c['label'] is not None:
                        c['label'] = str(c['label'])
                    connections_payload.append(c)
                except Exception as e:
                    self.logger.warning(f"Skipping connection during save due to error: {e}")
                    continue

            workflow_data = {
                'nodes': nodes_payload,
                'connections': connections_payload,
                'metadata': {
                    'version': '1.0',
                    'created_with': 'VERA'
                }
            }

            # Ensure extension
            target = Path(filename)
            if target.suffix.lower() != '.vsw':
                target = target.with_suffix('.vsw')

            # Atomic write to prevent truncated files
            tmp = target.with_suffix(target.suffix + '.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp, target)
            
            self.current_workflow_file = str(target)
            self.logger.info(f"Saved workflow to {self.current_workflow_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save workflow: {e}")
            return False
    
    def clear_workflow(self):
        """Clear the current workflow."""
        # Stop any running workflow and cleanup resources first
        if self.is_running:
            self.stop_workflow()

        # Terminate any active subprocesses
        try:
            self._terminate_all_processes()
        except Exception:
            pass

        with self._state_lock:
            self.nodes.clear()
            self.connections.clear()
            self.execution_order.clear()
            self.executed_nodes.clear()
            self.node_results.clear()
            self._run_nodes.clear()
            self._run_connections.clear()
        self.current_workflow_file = None
        
    def validate_workflow(self) -> tuple[bool, str]:
        """Validate the current workflow."""
        with self._state_lock:
            has_nodes = bool(self.nodes)
        if not has_nodes:
            return False, "Workflow is empty"
        
        # Check for cycles
        if self._has_cycles():
            return False, "Workflow contains cycles"
        
        # Validate individual nodes
        with self._state_lock:
            items = list(self.nodes.items())
        for node_id, node_data in items:
            valid, message = self._validate_node(node_data)
            if not valid:
                return False, f"Node {node_id}: {message}"
        
        # Build execution order
        self.execution_order = self._build_execution_order()
        if not self.execution_order:
            return False, "Cannot determine execution order"
        
        return True, "Workflow is valid"

    # --- Validation animation preview ---------------------------------------
    def play_validation_animation(self) -> None:
        """Play a brief sequential glow on nodes following the built execution order.

        Safe to call only after a successful validate_workflow() which populates execution_order.
        """
        try:
            # Do not animate while a workflow is running
            if self.is_running:
                # Nothing to do; immediately notify finished so UI can proceed
                try:
                    self.validation_animation_finished.emit()
                except Exception:
                    pass
                return
            if self._live_canvas is None:
                try:
                    self.validation_animation_finished.emit()
                except Exception:
                    pass
                return
            if not self.execution_order:
                # Best effort: attempt to sync from canvas and rebuild order
                try:
                    self.update_from_canvas(self._live_canvas)
                    self._sanitize_graph()
                    self.execution_order = self._build_execution_order()
                except Exception:
                    pass
            if not self.execution_order:
                try:
                    self.validation_animation_finished.emit()
                except Exception:
                    pass
                return

            # Initialize sequence
            self._validate_anim_order = list(self.execution_order)
            self._validate_anim_index = -1

            # Reset all to idle visually before starting
            for nid in self._validate_anim_order:
                try:
                    self.node_state_update.emit(nid, "idle")
                except Exception:
                    pass

            # Start timer
            if self._validate_anim_timer is not None:
                try:
                    if self._validate_anim_timer.isActive():
                        self._validate_anim_timer.stop()
                except Exception:
                    pass
                self._validate_anim_timer.start()
            else:
                try:
                    self.validation_animation_finished.emit()
                except Exception:
                    pass
        except Exception:
            try:
                self.validation_animation_finished.emit()
            except Exception:
                pass

    def _on_validate_anim_tick(self) -> None:
        """Advance the validation glow sequence one step on each tick."""
        try:
            order = self._validate_anim_order
            if not order:
                # Nothing to animate
                if self._validate_anim_timer is not None:
                    try:
                        self._validate_anim_timer.stop()
                    except Exception:
                        pass
                return

            # Turn previous back to idle
            if 0 <= self._validate_anim_index < len(order):
                prev_id = order[self._validate_anim_index]
                try:
                    self.node_state_update.emit(prev_id, "idle")
                except Exception:
                    pass

            # Advance index
            self._validate_anim_index += 1

            if self._validate_anim_index >= len(order):
                # Finished sequence
                if self._validate_anim_timer is not None:
                    try:
                        self._validate_anim_timer.stop()
                    except Exception:
                        pass
                # Ensure all nodes end in idle
                for nid in order:
                    try:
                        self.node_state_update.emit(nid, "idle")
                    except Exception:
                        pass
                try:
                    self.validation_animation_finished.emit()
                except Exception:
                    pass
                return

            # Light up current node briefly as "validating"
            curr_id = order[self._validate_anim_index]
            try:
                self.node_state_update.emit(curr_id, "validating")
            except Exception:
                pass
        except Exception:
            try:
                if self._validate_anim_timer is not None:
                    self._validate_anim_timer.stop()
            except Exception:
                pass
    
    def execute_workflow(self):
        """Execute the current workflow."""
        if self.is_running:
            self.logger.warning("Workflow is already running")
            return
        
        # Always refresh workflow state from the live canvas so node properties/graph
        # edited by the user are reflected in this run
        try:
            if self._live_canvas is not None:
                self.update_from_canvas(self._live_canvas)
        except Exception as e:
            self.logger.warning(f"Failed to sync from canvas before run: {e}")

        # Remove invalid/dangling connections before validation
        self._sanitize_graph()

        # Validate workflow first (robust to unexpected graph inconsistencies)
        try:
            valid, message = self.validate_workflow()
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            self.workflow_finished.emit(False, f"Validation error: {e}")
            return
        if not valid:
            self.workflow_finished.emit(False, f"Validation failed: {message}")
            return
        
        self.is_running = True
        self.is_paused = False
        self._pause_event.clear()
        self._stop_event.clear()
        self._user_stopped = False
        self.executed_nodes.clear()
        self.node_results.clear()
        
        # Snapshot current graph for this run
        with self._state_lock:
            self._run_nodes = dict(self.nodes)
            self._run_connections = dict(self.connections)

        # Reset all nodes to idle state
        self._reset_all_nodes_to_idle()
        
        self.workflow_started.emit()
        self.logger.info("Starting workflow execution")
        
        # Execute in separate thread
        self._current_thread = threading.Thread(target=self._execute_workflow_thread, daemon=True)
        self._current_thread.start()

    def execute_from_node(self, start_node_id: str) -> None:
        """Execute only from the given node downstream (partial re-run).

        - Assumes upstream results are available from a previous run.
        - Recomputes the start node and all nodes reachable from it.
        """
        try:
            # If this node was waiting for user input, just resume it (don't start new thread)
            if start_node_id in self.user_input_paused_nodes:
                self.logger.info(f"Resuming workflow from user input node {start_node_id}")
                self.resume_user_input(start_node_id)
                return  # Don't start new thread, just resume existing one
            
            # For normal partial rerun, workflow should not be running
            if self.is_running:
                self.logger.warning("Workflow is already running; ignoring partial re-run request")
                return
            # Sync latest canvas graph
            try:
                if self._live_canvas is not None:
                    self.update_from_canvas(self._live_canvas)
            except Exception as e:
                self.logger.warning(f"Failed to sync from canvas before partial run: {e}")

            # Remove invalid/dangling connections before validation
            self._sanitize_graph()

            # Validate and (re)build execution order (topo order)
            try:
                valid, message = self.validate_workflow()
            except Exception as e:
                self.workflow_finished.emit(False, f"Validation error: {e}")
                return
            if not valid:
                self.workflow_finished.emit(False, f"Validation failed: {message}")
                return

            if start_node_id not in self.nodes:
                self.workflow_finished.emit(False, f"Start node not found: {start_node_id}")
                return

            # Determine downstream set from start node
            downstream_nodes = self._collect_downstream_nodes(start_node_id)
            if not downstream_nodes:
                self.logger.info("No downstream nodes found for partial execution; nothing to do")
                return
            # Restrict to nodes present in topo order and keep their order
            run_order = [nid for nid in self.execution_order if nid in downstream_nodes]
            if not run_order:
                self.logger.info("Computed downstream set produced empty execution list; nothing to run")
                return

            # Prepare execution state for partial run
            self.is_running = True
            self.is_paused = False
            self._pause_event.clear()
            self._stop_event.clear()
            self._user_stopped = False
            # Do not clear self.node_results globally; keep upstream cached results
            # But clear results of nodes that will be re-executed
            for nid in run_order:
                if nid in self.node_results:
                    try:
                        del self.node_results[nid]
                    except Exception:
                        pass

            # Snapshot graph for this partial run
            with self._state_lock:
                self._run_nodes = dict(self.nodes)
                self._run_connections = dict(self.connections)

            # Set visual state: set affected nodes to idle to show they will run
            for nid in run_order:
                self.node_state_update.emit(nid, "idle")

            # Emit started (optional) and run in a background thread
            self.workflow_started.emit()
            self.logger.info(f"Starting partial execution from {start_node_id} ({len(run_order)} nodes)")

            def _partial_thread():
                try:
                    total = len(run_order)
                    paused_hint_for: str | None = None
                    for i, nid in enumerate(run_order):
                        if not self.is_running or self._stop_event.is_set():
                            break
                        while self._pause_event.is_set():
                            # Mark upcoming node as paused (yellow) and show hint once via UI thread
                            try:
                                self.node_state_update.emit(nid, "paused")
                                if paused_hint_for != nid:
                                    self.node_pause_hint.emit(nid, "Workflow paused here. Click Resume to continue.")
                                    paused_hint_for = nid
                            except Exception:
                                pass
                            if not self.is_running or self._stop_event.is_set():
                                break
                            time.sleep(0.05)
                        # Report progress relative to subset
                        try:
                            pct = int((i / max(1, total)) * 100)
                            self.progress_updated.emit(pct)
                        except Exception:
                            pass
                        # Visual running
                        self.node_state_update.emit(nid, "running")
                        try:
                            self.node_progress_updated.emit(nid, -1, "Updating…")
                        except Exception:
                            pass
                        # Execute node
                        self.node_started.emit(nid)
                        try:
                            success, msg = self._execute_node(nid)
                        except Exception as e:
                            success, msg = False, f"Node execution error: {str(e)}"
                        # If user input pause requested during partial run, wait and re-run this node
                        if nid in self.user_input_paused_nodes:
                            self.logger.info(f"Partial run paused at node {nid} - waiting for user input")
                            while nid in self.user_input_paused_nodes:
                                if not self.is_running or self._stop_event.is_set():
                                    break
                                time.sleep(0.1)
                            if not self.is_running or self._stop_event.is_set():
                                break
                            # Loop re-execution until no longer paused
                            while True:
                                self.node_state_update.emit(nid, "running")
                                try:
                                    self.node_progress_updated.emit(nid, -1, "Continuing…")
                                except Exception:
                                    pass
                                try:
                                    success, msg = self._execute_node(nid)
                                except Exception as e:
                                    success, msg = False, f"Node execution error: {str(e)}"
                                if nid in self.user_input_paused_nodes:
                                    while nid in self.user_input_paused_nodes:
                                        if not self.is_running or self._stop_event.is_set():
                                            break
                                        time.sleep(0.1)
                                    if not self.is_running or self._stop_event.is_set():
                                        break
                                    self.logger.info(f"Additional input completed for node {nid} - continuing")
                                    continue
                                break
                        if success:
                            try:
                                self.node_progress_updated.emit(nid, 100, "Completed")
                            except Exception:
                                pass
                            self.node_state_update.emit(nid, "completed")
                        else:
                            # Clear progress bar first, then show error
                            try:
                                self.node_progress_updated.emit(nid, None, "")
                            except Exception:
                                pass
                            self.node_state_update.emit(nid, "error")
                            try:
                                self.node_error_reported.emit(nid, msg)
                            except Exception:
                                pass
                            # Abort partial run on first failure
                            self.is_running = False
                            self.workflow_finished.emit(False, f"Partial run failed at {nid}: {msg}")
                            return
                        self.node_finished.emit(nid, success, msg)
                        time.sleep(0.05)
                    # Completed
                    if self._stop_event.is_set() or self._user_stopped:
                        try:
                            self.progress_updated.emit(max(0, int((len(self.executed_nodes) / max(1, total)) * 100)))
                        except Exception:
                            pass
                        self.is_running = False
                        # Reset all nodes to idle state to clear progress bars
                        self._reset_all_nodes_to_idle()
                        self.workflow_finished.emit(False, "Partial run stopped by user")
                    else:
                        self.progress_updated.emit(100)
                        self.is_running = False
                        # Reset all nodes to idle state to clear progress bars
                        self._reset_all_nodes_to_idle()
                        self.workflow_finished.emit(True, "Partial run completed successfully")
                except Exception as e:
                    self.is_running = False
                    self.workflow_finished.emit(False, f"Partial execution failed: {e}")
                finally:
                    # Always reset thread reference when thread completes
                    self._current_thread = None

            self._current_thread = threading.Thread(target=_partial_thread, daemon=True)
            self._current_thread.start()
        except Exception as e:
            self.is_running = False
            self.workflow_finished.emit(False, f"Partial execution setup failed: {e}")
    
    def stop_workflow(self):
        """Stop the current workflow execution."""
        if self.is_running:
            # Mark stop intent and signal worker
            self._user_stopped = True
            self.is_running = False
            self.is_paused = False
            self._pause_event.clear()
            self._stop_event.set()  # Signal stop to all threads
            self.logger.info("Stopping workflow execution")

            # Terminate any active external subprocesses immediately
            try:
                self._terminate_all_processes()
            except Exception:
                pass

            # Give thread time to cleanup gracefully
            if self._current_thread and self._current_thread.is_alive():
                self._current_thread.join(timeout=2)

    def pause_workflow(self):
        """Pause current workflow execution."""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self._pause_event.set()
            self.workflow_paused.emit()
            self.logger.info("Workflow paused")

    def resume_workflow(self):
        """Resume a paused workflow execution."""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self._pause_event.clear()
            self.workflow_resumed.emit()
            self.logger.info("Workflow resumed")
    
    def pause_user_input(self, node_id: str, message: str):
        """Pause workflow for user input at specific node (different from global pause)."""
        try:
            self.user_input_paused_nodes.add(node_id)
            self.user_input_paused.emit(node_id, message)
            self.logger.info(f"User input paused at node {node_id}: {message}")
        except Exception as e:
            self.logger.error(f"Failed to pause user input at node {node_id}: {e}")
    
    def resume_user_input(self, node_id: str):
        """Resume workflow after user input is completed at specific node."""
        try:
            if node_id in self.user_input_paused_nodes:
                self.user_input_paused_nodes.discard(node_id)
                # Sync latest properties from the live node back into manager snapshots
                # so the resumed execution sees the updated selections.
                try:
                    live_node = self._node_live_map.get(node_id)
                    if live_node is not None:
                        props = dict(getattr(live_node, "properties", {}) or {})
                        with self._state_lock:
                            if node_id in self.nodes:
                                try:
                                    self.nodes[node_id]["properties"] = dict(props)
                                except Exception:
                                    pass
                            if node_id in self._run_nodes:
                                try:
                                    self._run_nodes[node_id]["properties"] = dict(props)
                                except Exception:
                                    pass
                except Exception:
                    pass
                self.user_input_resumed.emit(node_id)
                self.logger.info(f"User input resumed at node {node_id}")
        except Exception as e:
            self.logger.error(f"Failed to resume user input at node {node_id}: {e}")
    
    def is_waiting_for_user_input(self, node_id: str) -> bool:
        """Check if a specific node is waiting for user input."""
        return node_id in self.user_input_paused_nodes
    
    def _execute_workflow_thread(self):
        """Execute workflow in separate thread."""
        try:
            total_nodes = len(self.execution_order)
            stopped_early = False
            paused_hint_for: str | None = None
            for i, node_id in enumerate(self.execution_order):
                # Check for stop signal
                if not self.is_running or self._stop_event.is_set():
                    self.logger.info("Workflow execution stopped")
                    stopped_early = True
                    break
                    
                # Pause gate
                while self._pause_event.is_set():
                    # Mark the upcoming node as paused (yellow) while waiting
                    try:
                        self.node_state_update.emit(node_id, "paused")
                        # Show a one-time floating yellow pause hint via UI-thread signal
                        if paused_hint_for != node_id:
                            self.node_pause_hint.emit(node_id, "Workflow paused here. Click Resume to continue.")
                            paused_hint_for = node_id
                    except Exception:
                        pass
                    if not self.is_running or self._stop_event.is_set():
                        stopped_early = True if self._stop_event.is_set() else False
                        break
                    time.sleep(0.05)
                
                # Update progress
                progress = int((i / total_nodes) * 100)
                self.progress_updated.emit(progress)
                
                # Update node visual state to running
                self.node_state_update.emit(node_id, "running")
                # Show indeterminate progress bar with a short status
                try:
                    self.node_progress_updated.emit(node_id, -1, "Starting…")
                except Exception:
                    pass
                
                # Execute node with timeout protection
                self.node_started.emit(node_id)
                try:
                    success, message = self._execute_node(node_id)
                except Exception as e:
                    success, message = False, f"Node execution error: {str(e)}"
                
                # After node execution, if node requested user input, wait and then
                # re-execute this same node so its outputs are produced immediately
                if node_id in self.user_input_paused_nodes:
                    self.logger.info(f"Workflow paused at node {node_id} - waiting for user input")
                    # Wait until user input is completed
                    while node_id in self.user_input_paused_nodes:
                        if not self.is_running or self._stop_event.is_set():
                            stopped_early = True
                            break
                        time.sleep(0.1)
                    if stopped_early:
                        break
                    self.logger.info(f"User input completed for node {node_id} - resuming execution")
                    # Re-run; if it asks again, loop until not paused
                    while True:
                        # Visual running indicators
                        self.node_state_update.emit(node_id, "running")
                        try:
                            self.node_progress_updated.emit(node_id, -1, "Continuing…")
                        except Exception:
                            pass
                        try:
                            success, message = self._execute_node(node_id)
                        except Exception as e:
                            success, message = False, f"Node execution error: {str(e)}"
                        if node_id in self.user_input_paused_nodes:
                            # Wait for additional input
                            while node_id in self.user_input_paused_nodes:
                                if not self.is_running or self._stop_event.is_set():
                                    stopped_early = True
                                    break
                                time.sleep(0.1)
                            if stopped_early:
                                break
                            self.logger.info(f"Additional input completed for node {node_id} - continuing")
                            continue
                        break
                
                # Update node visual state based on result
                if success:
                    # Finalize progress first, then mark completed (which hides bar)
                    try:
                        self.node_progress_updated.emit(node_id, 100, "Completed")
                    except Exception:
                        pass
                    self.node_state_update.emit(node_id, "completed")
                else:
                    # Clear progress bar first, then show error
                    try:
                        self.node_progress_updated.emit(node_id, None, "")
                    except Exception:
                        pass
                    self.node_state_update.emit(node_id, "error")
                    try:
                        self.node_error_reported.emit(node_id, message)
                    except Exception:
                        pass
                
                self.node_finished.emit(node_id, success, message)
                
                if not success:
                    # If user requested stop, treat as stopped instead of failure
                    if self._stop_event.is_set() or self._user_stopped:
                        self.logger.info("Aborting remaining nodes due to user stop request")
                        stopped_early = True
                        break
                    self.is_running = False
                    self.workflow_finished.emit(False, f"Node {node_id} failed: {message}")
                    return
                
                self.executed_nodes.add(node_id)
                
                # Brief pause to allow UI updates and cancellation checks
                time.sleep(0.1)
            
            # Decide final status based on stop flag
            if stopped_early or self._stop_event.is_set() or self._user_stopped:
                try:
                    self.progress_updated.emit(max(0, int((len(self.executed_nodes) / max(1, total_nodes)) * 100)))
                except Exception:
                    pass
                self.is_running = False
                # Reset all nodes to idle state to clear progress bars
                self._reset_all_nodes_to_idle()
                self.workflow_finished.emit(False, "Workflow stopped by user")
            else:
                # Workflow completed successfully
                self.progress_updated.emit(100)
                self.is_running = False
                # Reset all nodes to idle state to clear progress bars
                self._reset_all_nodes_to_idle()
                self.workflow_finished.emit(True, "Workflow completed successfully")

        except Exception as e:
            self.is_running = False
            self.workflow_finished.emit(False, f"Workflow execution failed: {e}")
        finally:
            # Always reset thread reference when thread completes
            self._current_thread = None
    
    def _execute_node(self, node_id: str) -> tuple[bool, str]:
        """Execute a single node with timeout protection."""
        node_data = self._run_nodes.get(node_id)
        if not node_data:
            return False, "Node not found"
        
        try:
            # Import node registry (classes) without instantiating Qt widgets
            from nodes import node_factory
            available = node_factory.get_available_nodes()
            node_type = node_data.get('type', 'unknown')
            NodeCls = available.get(node_type)
            if NodeCls is None:
                return False, f"Unknown node type: {node_type}"
            
            # Prepare inputs
            inputs = self._prepare_node_inputs(node_id)
            
            # Headless execution context to avoid creating any Qt objects in worker thread
            # Provides dynamic fallback to class helper methods via __getattr__.
            class _HeadlessContext:
                def __init__(self, properties: dict, logger, manager, _node_id: str):
                    self.properties = dict(properties or {})
                    self.logger = logger
                    self._manager = manager
                    self._node_id = _node_id
                def _log(self, message: object) -> None:
                    try:
                        text = str(message)
                    except Exception:
                        text = repr(message)
                    try:
                        self.logger.info(text)
                    except Exception:
                        try:
                            print(f"[Headless] {text}")
                        except Exception:
                            pass
                def get_property(self, key, default=None):
                    return self.properties.get(key, default)
                def set_property(self, key, value):
                    self.properties[key] = value
                def report_progress(self, percent: int = -1, message: str | None = None) -> None:
                    """Report per-node progress back to the GUI.

                    percent < 0 => indeterminate bar
                    0..100 => determinate progress
                    """
                    try:
                        msg = "" if message is None else str(message)
                        self._manager.node_progress_updated.emit(self._node_id, int(percent), msg)
                    except Exception:
                        pass
                def report_log(self, line: str) -> None:
                    """Report a log line to be appended under the node in the UI."""
                    try:
                        self._manager.node_log_appended.emit(self._node_id, str(line))
                    except Exception:
                        pass
                def register_subprocess(self, proc) -> None:
                    """Register a subprocess so it can be terminated on stop.

                    Nodes call this to allow the manager to keep track of external processes.
                    """
                    try:
                        self._manager._register_subprocess(self._node_id, proc)
                    except Exception:
                        pass
                def unregister_subprocess(self, proc = None) -> None:
                    """Unregister a subprocess previously registered by the node."""
                    try:
                        self._manager._unregister_subprocess(self._node_id, proc)
                    except Exception:
                        pass
                def __getattr__(self, name: str):
                    # Allow access to class-level helper methods as if they were bound
                    try:
                        attr = getattr(NodeCls, name)
                    except Exception:
                        attr = None
                    if callable(attr):
                        def _bound(*args, **kwargs):
                            return attr(self, *args, **kwargs)
                        return _bound
                    if attr is not None:
                        return attr
                    raise AttributeError(f"'_HeadlessContext' object has no attribute '{name}'")
                def _summarize(self, d):
                    """Basic summarization for headless execution."""
                    try:
                        if isinstance(d, dict):
                            items = list(d.items())[:5]
                            return "\n".join(f"{k}: {str(v)[:60]}{'...' if len(str(v))>60 else ''}" for k, v in items)
                        if isinstance(d, list):
                            return "\n".join(str(x)[:60] + ("..." if len(str(x)) > 60 else "") for x in d[:5])
                        return str(d)
                    except Exception:
                        return str(d)
            
            headless_self = _HeadlessContext(node_data.get('properties', {}), self.logger, self, node_id)
            
            # Execute node logic by calling the unbound execute method on a dummy context
            self.logger.info(f"Executing node {node_id} ({node_type})")
            result = NodeCls.execute(headless_self, inputs)
            
            # Validate result
            if result is None:
                result = {}
            
            # Store result
            self.node_results[node_id] = result

            # Write back any mutated properties to snapshots and live state
            try:
                node_data['properties'] = dict(headless_self.properties or {})
                self._run_nodes[node_id] = node_data
                with self._state_lock:
                    if node_id in self.nodes:
                        self.nodes[node_id] = node_data
            except Exception:
                pass

            # Emit signal with error protection
            try:
                self.node_result_emitted.emit(node_id, result, inputs)
            except Exception as e:
                self.logger.warning(f"Failed to emit node result signal: {e}")
            
            self.logger.info(f"Node {node_id} executed successfully")
            return True, "Node executed successfully"
            
        except ValueError as e:
            # Network/timeout errors from scrapers
            error_msg = str(e)
            self.logger.error(f"Node {node_id} failed: {error_msg}")
            return False, error_msg
            
        except Exception as e:
            # General execution errors
            error_msg = f"Execution error: {str(e)}"
            self.logger.error(f"Node {node_id} failed with exception: {e}")
            return False, error_msg
    
    def _prepare_node_inputs(self, node_id: str) -> Dict[str, Any]:
        """Prepare inputs for a node based on connections."""
        inputs = {}
        
        # Find input connections for this node
        for conn_data in self._run_connections.values():
            if conn_data['target_node'] == node_id:
                source_node = conn_data['source_node']
                source_port = conn_data['source_port']
                target_port = conn_data['target_port']
                
                # Get result from source node
                if source_node in self.node_results:
                    source_result = self.node_results[source_node]
                    if isinstance(source_result, dict) and source_port in source_result:
                        inputs[target_port] = source_result[source_port]
                    else:
                        inputs[target_port] = source_result
        
        return inputs

    def _collect_downstream_nodes(self, start_node_id: str) -> set[str]:
        """Return the set of nodes reachable from start_node_id, including itself."""
        reachable: set[str] = set()
        with self._state_lock:
            nodes_keys = set(self.nodes.keys())
            conns = list(self.connections.values())
        if start_node_id not in nodes_keys:
            return reachable
        # Build adjacency list only for valid nodes
        out_edges: dict[str, list[str]] = {}
        for conn in conns:
            try:
                src = conn.get('source_node')
                dst = conn.get('target_node')
                if src not in nodes_keys or dst not in nodes_keys:
                    continue
                if src not in out_edges:
                    out_edges[src] = []
                out_edges[src].append(dst)
            except Exception:
                continue
        # BFS
        queue: list[str] = [start_node_id]
        while queue:
            nid = queue.pop(0)
            if nid in reachable:
                continue
            reachable.add(nid)
            for nxt in out_edges.get(nid, []):
                if nxt not in reachable:
                    queue.append(nxt)
        return reachable
    
    def _validate_node(self, node_data: Dict) -> tuple[bool, str]:
        """Validate a single node."""
        # Check required fields
        if 'type' not in node_data:
            return False, "Node type not specified"
        
        if 'id' not in node_data:
            return False, "Node ID not specified"
        
        # Node-specific validation would go here
        return True, "Node is valid"
    
    def _has_cycles(self) -> bool:
        """Check if the workflow has cycles."""
        # Simple cycle detection using DFS
        visited = set()
        rec_stack = set()
        
        def dfs(node_id):
            visited.add(node_id)
            rec_stack.add(node_id)
            
            # Get downstream nodes
            with self._state_lock:
                conns = list(self.connections.values())
            for conn_data in conns:
                if conn_data['source_node'] == node_id:
                    neighbor = conn_data['target_node']
                    if neighbor not in visited:
                        if dfs(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
            
            rec_stack.remove(node_id)
            return False
        
        with self._state_lock:
            node_ids = list(self.nodes.keys())
        for node_id in node_ids:
            if node_id not in visited:
                if dfs(node_id):
                    return True
        
        return False
    
    def _build_execution_order(self) -> List[str]:
        """Build topological order for execution."""
        # Calculate in-degrees
        with self._state_lock:
            node_ids = list(self.nodes.keys())
            conns = list(self.connections.values())
        in_degree = {node_id: 0 for node_id in node_ids}
        
        for conn_data in conns:
            try:
                src = conn_data.get('source_node')
                dst = conn_data.get('target_node')
            except Exception:
                continue
            if src not in in_degree or dst not in in_degree:
                # Ignore dangling connections referencing non-existent nodes
                continue
            in_degree[dst] += 1
        
        # Topological sort
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            node_id = queue.pop(0)
            result.append(node_id)
            
            # Update in-degrees of downstream nodes
            for conn_data in conns:
                try:
                    src = conn_data.get('source_node')
                    target = conn_data.get('target_node')
                except Exception:
                    continue
                if src != node_id:
                    continue
                if target not in in_degree:
                    continue
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)
        
        return result if len(result) == len(node_ids) else []
    
    def cleanup(self):
        """Cleanup resources."""
        if self.is_running:
            self.stop_workflow()
        # Ensure any stray external processes are terminated
        try:
            self._terminate_all_processes()
        except Exception:
            pass
        self.logger.info("Workflow manager cleaned up")

    # ---- External process management ----
    def _register_subprocess(self, node_id: str, proc):
        try:
            with self._active_process_lock:
                lst = self._active_processes.get(node_id)
                if lst is None:
                    lst = []
                    self._active_processes[node_id] = lst
                if proc not in lst:
                    lst.append(proc)
        except Exception:
            pass

    def _unregister_subprocess(self, node_id: str, proc = None) -> None:
        try:
            with self._active_process_lock:
                if node_id not in self._active_processes:
                    return
                if proc is None:
                    self._active_processes.pop(node_id, None)
                    return
                lst = self._active_processes.get(node_id) or []
                try:
                    if proc in lst:
                        lst.remove(proc)
                except Exception:
                    pass
                if not lst:
                    self._active_processes.pop(node_id, None)
        except Exception:
            pass

    def _terminate_all_processes(self) -> None:
        """Terminate all registered external processes immediately.

        On Windows, also attempt to kill the whole process tree via taskkill.
        """
        try:
            with self._active_process_lock:
                items = list(self._active_processes.items())
                self._active_processes.clear()
        except Exception:
            items = []
        for _node_id, procs in items:
            for proc in list(procs or []):
                if proc is None:
                    continue
                try:
                    if sys.platform.startswith('win'):
                        try:
                            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, timeout=2, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        except Exception:
                            pass
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    try:
                        proc.kill()
                    except Exception:
                        pass
                except Exception:
                    pass
