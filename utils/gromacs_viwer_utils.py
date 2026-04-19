import sys
import os
import math
import struct
import hashlib
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import Qt, Signal, QThread, QMutex, QMutexLocker
from PySide6 import QtOpenGLWidgets
from PySide6.QtGui import QAction

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    import OpenGL.GL as gl
except ImportError:
    print("PyOpenGL not found. Exiting...")
    sys.exit(1)

# Optional GPU acceleration
try:
    import pyopencl as cl  # type: ignore
    _HAS_PYOPENCL = True
except Exception:
    _HAS_PYOPENCL = False
    print("PyOpenCL not found. Using CPU only.")


from backend.temp_manager import get_subdir


# OpenCL context/program (lazy)
_CL_CTX = None
_CL_QUEUE = None
_CL_PROG = None

def _init_opencl_once():
    global _CL_CTX, _CL_QUEUE, _CL_PROG
    if not _HAS_PYOPENCL:
        return False
    if _CL_CTX is not None:
        return True
    try:
        # Prefer GPU device
        platforms = cl.get_platforms()
        devices = []
        for p in platforms:
            try:
                devices.extend(p.get_devices(device_type=cl.device_type.GPU))
            except Exception:
                pass
        if not devices:
            # Fallback to any device
            for p in platforms:
                try:
                    devices.extend(p.get_devices())
                except Exception:
                    pass
        if not devices:
            return False
        _CL_CTX = cl.Context(devices=[devices[0]])
        _CL_QUEUE = cl.CommandQueue(_CL_CTX)
        src = """
        __kernel void build_rings(
            __global const float* centers,
            __global const float* Ns,
            __global const float* Bs,
            const float radius,
            const int ring_slices,
            const int num_centers,
            __global float* out_vertices,
            __global float* out_normals)
        {
            int gid = get_global_id(0);
            int i = gid / ring_slices;
            int k = gid % ring_slices;
            if (i >= num_centers) return;
            const float PI = 3.14159265358979323846f;
            float theta = (2.0f * PI * (float)k) / (float)ring_slices;
            int base3 = i * 3;
            float cx = centers[base3 + 0];
            float cy = centers[base3 + 1];
            float cz = centers[base3 + 2];
            float Nx = Ns[base3 + 0];
            float Ny = Ns[base3 + 1];
            float Nz = Ns[base3 + 2];
            float Bx = Bs[base3 + 0];
            float By = Bs[base3 + 1];
            float Bz = Bs[base3 + 2];
            float cth = cos(theta);
            float sth = sin(theta);
            float offx = (cth * Nx + sth * Bx) * radius;
            float offy = (cth * Ny + sth * By) * radius;
            float offz = (cth * Nz + sth * Bz) * radius;
            float vx = cx + offx;
            float vy = cy + offy;
            float vz = cz + offz;
            // normal is normalized offset
            float len = sqrt(offx*offx + offy*offy + offz*offz);
            float nx = offx, ny = offy, nz = offz;
            if (len > 1e-6f) { nx /= len; ny /= len; nz /= len; }
            int out3 = (i * ring_slices + k) * 3;
            out_vertices[out3 + 0] = vx;
            out_vertices[out3 + 1] = vy;
            out_vertices[out3 + 2] = vz;
            out_normals[out3 + 0] = nx;
            out_normals[out3 + 1] = ny;
            out_normals[out3 + 2] = nz;
        }
        """
        _CL_PROG = cl.Program(_CL_CTX, src).build()
        return True
    except Exception:
        _CL_CTX = None
        _CL_QUEUE = None
        _CL_PROG = None
        return False

# Atomic radii in Angstroms
ATOMIC_RADII = {
    'H': 0.31, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'P': 1.07, 'S': 1.05,
    'CA': 1.00, 'MG': 0.72, 'FE': 0.64, 'ZN': 0.74, 'CL': 0.99, 'NA': 1.02,
    'K': 1.38, 'CU': 0.73, 'MN': 0.67
}

# CPK colors for atoms
ATOMIC_COLORS = {
    'H': (1.0, 1.0, 1.0),    # White
    'C': (0.3, 0.3, 0.3),    # Dark gray
    'N': (0.0, 0.0, 1.0),    # Blue
    'O': (1.0, 0.0, 0.0),    # Red
    'P': (1.0, 0.5, 0.0),    # Orange
    'S': (1.0, 1.0, 0.0),    # Yellow
    'CA': (0.0, 1.0, 0.0),   # Green
    'MG': (0.5, 1.0, 0.5),   # Light green
    'FE': (1.0, 0.5, 0.0),   # Orange
    'ZN': (0.5, 0.5, 0.5),   # Gray
    'CL': (0.0, 1.0, 0.0),   # Green
    'NA': (0.0, 0.0, 1.0),   # Blue
    'K': (1.0, 0.0, 1.0),    # Magenta
    'CU': (0.8, 0.5, 0.2),   # Brown
    'MN': (0.8, 0.0, 0.8),   # Purple
}

# Approximate covalent radii in Angstroms (used for bond inference)
COVALENT_RADII = {
    'H': 0.31, 'C': 0.76, 'N': 0.71, 'O': 0.66, 'P': 1.07, 'S': 1.05,
    'F': 0.57, 'CL': 0.99, 'BR': 1.14, 'I': 1.33,
    'CA': 1.76, 'MG': 1.41, 'NA': 1.66, 'K': 2.03, 'ZN': 1.22, 'FE': 1.24, 'CU': 1.32, 'MN': 1.39
}

# Water residue names
WATER_RESIDUES = {'SOL', 'TIP3', 'TIP4', 'TIP5', 'SPC', 'HOH', 'WAT'}

# Protein residue names  
PROTEIN_RESIDUES = {
    'ALA', 'ARG', 'ASN', 'ASP', 'CYS', 'GLN', 'GLU', 'GLY', 'HIS', 'ILE',
    'LEU', 'LYS', 'MET', 'PHE', 'PRO', 'SER', 'THR', 'TRP', 'TYR', 'VAL',
    'SEC', 'PYL'  # Extended amino acids
}

# Ion names
ION_RESIDUES = {'NA', 'CL', 'K', 'CA', 'MG', 'ZN', 'FE', 'CU', 'MN'}

class Atom:
    def __init__(self, atom_id: int, atom_name: str, residue_name: str, 
                 residue_id: int, x: float, y: float, z: float, chain: str = 'A'):
        self.atom_id = atom_id
        self.atom_name = atom_name.strip()
        self.residue_name = residue_name.strip()
        self.residue_id = residue_id
        self.chain = chain
        self.x = x
        self.y = y
        self.z = z
        
        # Determine element from atom name
        self.element = self._get_element()
        self.radius = ATOMIC_RADII.get(self.element, 0.5)
        self.color = ATOMIC_COLORS.get(self.element, (0.5, 0.5, 0.5))
        
        # Classification
        self.is_water = self.residue_name in WATER_RESIDUES
        self.is_protein = self.residue_name in PROTEIN_RESIDUES
        self.is_ion = self.residue_name in ION_RESIDUES
        self.is_nucleic = self.residue_name in {'DA', 'DT', 'DG', 'DC', 'A', 'T', 'G', 'C', 'U'}
        
        # Selection flag
        self.selected = True
    
    def _get_element(self) -> str:
        name = self.atom_name.upper()
        # Handle calcium specifically
        if name == 'CA' and self.residue_name in ION_RESIDUES:
            return 'CA'
        # Handle backbone CA
        elif name == 'CA' and self.residue_name in PROTEIN_RESIDUES:
            return 'C'
        elif name[0] in 'HCNOPSFEMG':
            return name[0]
        elif len(name) >= 2 and name[:2] in ['CA', 'MG', 'FE', 'ZN', 'CL', 'NA', 'CU', 'MN']:
            return name[:2]
        else:
            return 'C'  # Default

class Frame:
    def __init__(self, atoms: List[Atom], box: Optional[List[float]] = None):
        self.atoms = atoms
        self.box = box or [0.0, 0.0, 0.0]
        self.time = 0.0
        
    def get_center(self, selected_only: bool = True) -> Tuple[float, float, float]:
        atoms_to_use = [atom for atom in self.atoms if atom.selected] if selected_only else self.atoms
        if not atoms_to_use:
            return (0.0, 0.0, 0.0)
        
        x = sum(atom.x for atom in atoms_to_use) / len(atoms_to_use)
        y = sum(atom.y for atom in atoms_to_use) / len(atoms_to_use)
        z = sum(atom.z for atom in atoms_to_use) / len(atoms_to_use)
        return (x, y, z)
    
    def get_selected_atoms(self) -> List[Atom]:
        return [atom for atom in self.atoms if atom.selected]

class SelectionParser:
    @staticmethod
    def parse_selection(selection: str, atoms: List[Atom]) -> List[Atom]:
        """Parse VMD-like selection commands with boolean logic and bare residue names.
        Supports: AND, OR, NOT, parentheses, keywords (protein, water, ion, nucleic, ligand),
        and predicates: resname, resid, name, element, chain. Bare tokens like 'DCK'/'UNL'
        are treated as residue names.
        """
        text = (selection or "").strip()
        if not text or text.lower() == "all":
            return atoms

        # Build a set of observed residue names for auto-detection of bare tokens
        observed_resnames = {a.residue_name.upper() for a in atoms}

        # Tokenize while keeping parentheses
        def tokenize(expr: str) -> List[str]:
            buf = []
            tok = ''
            for ch in expr:
                if ch in '()':
                    if tok:
                        buf.append(tok)
                        tok = ''
                    buf.append(ch)
                elif ch.isspace():
                    if tok:
                        buf.append(tok)
                        tok = ''
                else:
                    tok += ch
            if tok:
                buf.append(tok)
            return buf

        tokens = tokenize(text)
        pos = 0

        def peek() -> Optional[str]:
            return tokens[pos] if pos < len(tokens) else None

        def consume() -> Optional[str]:
            nonlocal pos
            t = peek()
            pos += 1
            return t

        # Parser returns a predicate: Atom -> bool
        def parse_expression():
            pred = parse_term()
            while True:
                t = peek()
                if t and t.lower() == 'or':
                    consume()
                    right = parse_term()
                    left = pred
                    pred = (lambda l=left, r=right: (lambda a: l(a) or r(a)))
                else:
                    break
            return pred

        def parse_term():
            pred = parse_factor()
            while True:
                t = peek()
                if t and t.lower() == 'and':
                    consume()
                    right = parse_factor()
                    left = pred
                    pred = (lambda l=left, r=right: (lambda a: l(a) and r(a)))
                else:
                    break
            return pred

        def parse_factor():
            t = peek()
            if t is None:
                return lambda a: True
            if t.lower() == 'not':
                consume()
                p = parse_factor()
                return lambda a, p=p: not p(a)
            if t == '(':
                consume()
                p = parse_expression()
                if peek() == ')':
                    consume()
                return p
            return parse_predicate()

        def collect_values() -> List[str]:
            vals: List[str] = []
            while True:
                t = peek()
                if t is None:
                    break
                tl = t.lower()
                if t in (')',) or tl in ('and', 'or', 'not'):
                    break
                vals.append(consume())
            return vals

        def parse_predicate():
            t = consume()
            if t is None:
                return lambda a: True
            tl = t.lower()

            if tl == 'protein':
                return lambda a: a.is_protein
            if tl == 'water':
                return lambda a: a.is_water
            if tl in ('ion', 'ions'):
                return lambda a: a.is_ion
            if tl == 'nucleic':
                return lambda a: a.is_nucleic
            if tl == 'ligand':
                return lambda a: (not a.is_protein and not a.is_water and not a.is_ion and not a.is_nucleic)
            if tl == 'backbone':
                backbone_names = {'N', 'CA', 'C', 'O'}
                return lambda a, bb=backbone_names: a.atom_name.upper() in bb
            if tl == 'sidechain':
                backbone_names = {'N', 'CA', 'C', 'O'}
                return lambda a, bb=backbone_names: (a.is_protein and a.atom_name.upper() not in bb)
            if tl == 'secondary' or tl == 'cartoon':
                # Placeholder predicate; actual cartoon uses protein atoms
                return lambda a: a.is_protein
            if tl == 'resname':
                vals = [v.upper() for v in collect_values()]
                return lambda a, vs=set(vals): a.residue_name.upper() in vs
            if tl == 'resid':
                vals = collect_values()
                try:
                    ids = set(int(v) for v in vals)
                except Exception:
                    ids = set()
                return lambda a, ids=ids: a.residue_id in ids
            if tl == 'name':
                vals = [v.upper() for v in collect_values()]
                return lambda a, vs=set(vals): a.atom_name.upper() in vs
            if tl == 'element':
                vals = [v.upper() for v in collect_values()]
                return lambda a, vs=set(vals): a.element.upper() in vs
            if tl == 'chain':
                vals = [v.upper() for v in collect_values()]
                return lambda a, vs=set(vals): a.chain.upper() in vs
            if tl == 'all':
                return lambda a: True

            # Bare token: treat as residue name if it looks like one or is observed
            token_upper = t.upper()
            if token_upper in observed_resnames or (2 <= len(token_upper) <= 4 and token_upper.isalnum()):
                return lambda a, rn=token_upper: a.residue_name.upper() == rn

            # Fallback: match nothing to avoid accidental full selection
            return lambda a: False

        predicate = parse_expression()
        return [atom for atom in atoms if predicate(atom)]

class XTCReader:
    """Improved XTC file reader with better error handling"""
    
    @staticmethod
    def _read_int(f):
        data = f.read(4)
        if len(data) != 4:
            return None
        return struct.unpack('>I', data)[0]
    
    @staticmethod
    def _read_float(f):
        data = f.read(4)
        if len(data) != 4:
            return None
        return struct.unpack('>f', data)[0]
    
    @staticmethod
    def _skip_bytes(f, n):
        """Skip n bytes in file"""
        return f.read(n)
    
    @staticmethod
    def read_xtc_frame(f, natoms: int):
        """Read a single XTC frame with improved error handling"""
        try:
            # Read magic number
            magic = XTCReader._read_int(f)
            if magic is None or magic != 1995:
                return None
                
            # Read natoms
            file_natoms = XTCReader._read_int(f)
            if file_natoms is None:
                return None
                
            # Sometimes natoms might be slightly different due to different counting
            # Let's be more flexible here
            if abs(file_natoms - natoms) > natoms * 0.1:  # Allow 10% difference
                print(f"Warning: natoms mismatch: expected {natoms}, got {file_natoms}")
                return None
                
            # Read step
            step = XTCReader._read_int(f)
            if step is None:
                return None
            
            # Read time
            time = XTCReader._read_float(f)
            if time is None:
                return None
            
            # Read box (9 floats)
            box = []
            for _ in range(9):
                box_val = XTCReader._read_float(f)
                if box_val is None:
                    return None
                box.append(box_val)
            
            # Read coordinates - try different approaches
            coordinates = []
            
            # First, check if there's a precision value
            current_pos = f.tell()
            precision = XTCReader._read_float(f)
            
            if precision is None:
                return None
                
            if precision == 0.0:
                # Uncompressed coordinates - read directly
                for i in range(file_natoms * 3):
                    coord = XTCReader._read_float(f)
                    if coord is None:
                        return None
                    coordinates.append(coord)
                    
            elif precision > 0:
                # Compressed coordinates - try to skip or read simplified
                print(f"Compressed XTC frame detected (precision: {precision})")
                
                # Try to estimate compressed data size and skip
                # This is a rough estimate - real XTC compression is complex
                estimated_size = file_natoms * 3 * 2  # Rough estimate
                XTCReader._skip_bytes(f, estimated_size)
                
                # Create dummy coordinates for now
                for i in range(file_natoms * 3):
                    coordinates.append(0.0)
                
                return None  # Skip compressed frames for now
            else:
                # Invalid precision value
                return None
                
            # Use actual natoms from file
            actual_coords = coordinates[:file_natoms * 3]
                
            return {
                'step': step,
                'time': time,
                'box': box[:3],  # Just diagonal elements
                'coordinates': actual_coords,
                'natoms': file_natoms
            }
            
        except struct.error as e:
            print(f"Struct error reading XTC frame: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error reading XTC frame: {e}")
            return None

class GromacsReader:
    @staticmethod
    def read_gro_file(filename: str) -> Frame:
        """Read GROMACS .gro file"""
        atoms = []
        
        with open(filename, 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 3:
            raise ValueError("Invalid GRO file format")
        
        title = lines[0].strip()
        num_atoms = int(lines[1].strip())
        
        for i in range(2, 2 + num_atoms):
            line = lines[i]
            if len(line) < 44:
                continue
                
            residue_id = int(line[0:5].strip())
            residue_name = line[5:10].strip()
            atom_name = line[10:15].strip()
            atom_id = int(line[15:20].strip())
            x = float(line[20:28]) * 10  # nm to Angstrom
            y = float(line[28:36]) * 10
            z = float(line[36:44]) * 10
            
            atom = Atom(atom_id, atom_name, residue_name, residue_id, x, y, z)
            atoms.append(atom)
        
        # Read box if present
        box = [0.0, 0.0, 0.0]
        if len(lines) > 2 + num_atoms:
            box_line = lines[2 + num_atoms].strip().split()
            if len(box_line) >= 3:
                box = [float(x) * 10 for x in box_line[:3]]  # nm to Angstrom
        
        return Frame(atoms, box)
    
    @staticmethod
    def read_xtc_file(filename: str, gro_frame: Frame, progress_callback=None, gro_topology_path: Optional[str] = None) -> List[Frame]:
        """Read GROMACS .xtc trajectory file.
        If MDAnalysis is available and a GRO topology path is provided, use it for robust reading
        (supports compressed XTC). Otherwise, fall back to a minimal reader.
        """
        frames = []
        natoms = len(gro_frame.atoms)
        
        print(f"Reading XTC file: {filename}")
        print(f"Expected natoms: {natoms}")

        # Preferred path: use MDAnalysis for robust XTC reading
        if gro_topology_path:
            try:
                import MDAnalysis as mda
                print("Using MDAnalysis to read trajectory")
                u = mda.Universe(gro_topology_path, filename)
                frame_count = 0
                for ts in u.trajectory:
                    atoms_new: List[Atom] = []
                    # MDAnalysis uses Angstrom units for positions
                    for i in range(min(len(gro_frame.atoms), u.atoms.n_atoms)):
                        pos = ts.positions[i]  # Angstrom
                        template_atom = gro_frame.atoms[i]
                        atom = Atom(
                            template_atom.atom_id,
                            template_atom.atom_name,
                            template_atom.residue_name,
                            template_atom.residue_id,
                            float(pos[0]),
                            float(pos[1]),
                            float(pos[2]),
                            template_atom.chain
                        )
                        atom.is_water = template_atom.is_water
                        atom.is_protein = template_atom.is_protein
                        atom.is_ion = template_atom.is_ion
                        atom.is_nucleic = template_atom.is_nucleic
                        atoms_new.append(atom)
                    box = [float(ts.dimensions[0]), float(ts.dimensions[1]), float(ts.dimensions[2])] if hasattr(ts, 'dimensions') and ts.dimensions is not None else gro_frame.box
                    frame = Frame(atoms_new, box)
                    if hasattr(ts, 'time') and ts.time is not None:
                        frame.time = float(ts.time)
                    else:
                        frame.time = frame_count
                    frames.append(frame)
                    frame_count += 1
                    if progress_callback:
                        progress_callback(frame_count)
                print(f"Successfully read {len(frames)} frames via MDAnalysis")
                return frames
            except ImportError:
                print("MDAnalysis not installed; falling back to basic XTC reader")
            except Exception as e:
                print(f"MDAnalysis failed to read XTC: {e}. Falling back to basic reader.")

        # Fallback: minimal XTC reader (limited support)
        try:
            file_size = Path(filename).stat().st_size
            print(f"File size: {file_size} bytes")
            
            with open(filename, 'rb') as f:
                frame_count = 0
                bytes_read = 0
                
                while True:
                    try:
                        current_pos = f.tell()
                        frame_data = XTCReader.read_xtc_frame(f, natoms)
                        
                        if frame_data is None:
                            # Try to skip some bytes and continue
                            if current_pos == f.tell():  # No bytes were read
                                # Try to skip ahead a bit
                                test_data = f.read(100)
                                if not test_data:
                                    break  # End of file
                                continue
                            else:
                                break  # Proper end of frame
                                
                        # Create atoms with new coordinates
                        atoms = []
                        coords = frame_data['coordinates']
                        actual_natoms = frame_data.get('natoms', natoms)
                        
                        # Handle natoms mismatch
                        atoms_to_create = min(len(gro_frame.atoms), actual_natoms)
                        
                        for i in range(atoms_to_create):
                            if i * 3 + 2 < len(coords):
                                x = coords[i * 3] * 10      # nm to Angstrom
                                y = coords[i * 3 + 1] * 10
                                z = coords[i * 3 + 2] * 10
                                
                                template_atom = gro_frame.atoms[i]
                                atom = Atom(template_atom.atom_id, template_atom.atom_name,
                                          template_atom.residue_name, template_atom.residue_id,
                                          x, y, z, template_atom.chain)
                                
                                # Copy properties
                                atom.is_water = template_atom.is_water
                                atom.is_protein = template_atom.is_protein
                                atom.is_ion = template_atom.is_ion
                                atom.is_nucleic = template_atom.is_nucleic
                                atoms.append(atom)
                        
                        if len(atoms) > 0:
                            frame = Frame(atoms, frame_data['box'])
                            frame.time = frame_data['time']
                            frames.append(frame)
                            frame_count += 1
                            
                            if progress_callback:
                                progress_callback(frame_count)
                                
                            # Progress based on file position
                            bytes_read = f.tell()
                            if frame_count % 10 == 0:  # Print every 10 frames
                                progress_pct = (bytes_read / file_size) * 100
                                print(f"Read {frame_count} frames ({progress_pct:.1f}%)")
                                
                            # Memory limit
                            if frame_count >= 2000:  # Limit to avoid memory blow-up
                                print(f"Reached frame limit of 2000")
                                break
                                
                    except Exception as e:
                        print(f"Error reading frame {frame_count}: {e}")
                        # Try to continue reading
                        continue
                        
        except FileNotFoundError:
            print(f"XTC file not found: {filename}")
            return GromacsReader._create_demo_frames(gro_frame, 50)
        except Exception as e:
            print(f"Error reading XTC file: {e}")
            import traceback
            traceback.print_exc()
            return GromacsReader._create_demo_frames(gro_frame, 50)
        
        print(f"Successfully read {len(frames)} frames from XTC file")
        
        if not frames:
            print("No frames read, creating demo frames")
            return GromacsReader._create_demo_frames(gro_frame, 50)
        
        return frames
    
    @staticmethod
    def _create_demo_frames(gro_frame: Frame, num_frames: int) -> List[Frame]:
        """Create demo frames with random movement"""
        frames = []
        
        for i in range(num_frames):
            atoms = []
            for atom in gro_frame.atoms:
                # Add small random movement
                dx = np.random.normal(0, 0.05)
                dy = np.random.normal(0, 0.05)
                dz = np.random.normal(0, 0.05)
                
                # Add oscillation
                osc = 0.1 * math.sin(i * 0.1)
                
                new_atom = Atom(atom.atom_id, atom.atom_name, atom.residue_name,
                              atom.residue_id, 
                              atom.x + dx + osc, 
                              atom.y + dy + osc * 0.5, 
                              atom.z + dz + osc * 0.8)
                new_atom.is_water = atom.is_water
                new_atom.is_protein = atom.is_protein
                new_atom.is_ion = atom.is_ion
                new_atom.is_nucleic = atom.is_nucleic
                atoms.append(new_atom)
                
            frame = Frame(atoms, gro_frame.box)
            frame.time = i * 0.1  # 0.1 ps per frame
            frames.append(frame)
        
        return frames

class BaseTrajectoryProvider:
    def get_num_frames(self) -> int:
        return 1
    def get_positions(self, frame_index: int):
        raise NotImplementedError
    def get_time(self, frame_index: int) -> float:
        return float(frame_index)
    def get_box(self, frame_index: int):
        return [0.0, 0.0, 0.0]
    @property
    def has_random_access(self) -> bool:
        return True

class SingleFrameProvider(BaseTrajectoryProvider):
    def __init__(self, atoms: List[Atom], box: List[float]):
        self._positions = [(a.x, a.y, a.z) for a in atoms]
        self._box = box
    def get_positions(self, frame_index: int):
        return self._positions
    def get_box(self, frame_index: int):
        return self._box

class MDAnalysisProvider(BaseTrajectoryProvider):
    def __init__(self, gro_path: str, xtc_path: str):
        import MDAnalysis as mda
        self._u = mda.Universe(gro_path, xtc_path)
        self._n = len(self._u.trajectory)
    def get_num_frames(self) -> int:
        return self._n
    def get_positions(self, frame_index: int):
        ts = self._u.trajectory[frame_index]
        return ts.positions
    def get_time(self, frame_index: int) -> float:
        ts = self._u.trajectory[frame_index]
        return float(getattr(ts, 'time', frame_index))
    def get_box(self, frame_index: int):
        ts = self._u.trajectory[frame_index]
        if hasattr(ts, 'dimensions') and ts.dimensions is not None:
            return [float(ts.dimensions[0]), float(ts.dimensions[1]), float(ts.dimensions[2])]
        return [0.0, 0.0, 0.0]

##############################################
# Precomputation and caching utilities
##############################################

class PrecomputedCartoonStore:
    """On-disk storage for per-frame precomputed cartoon arrays.
    Stores three .npy files per frame: vertices, normals, colors.
    """
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        try:
            os.makedirs(self.root_dir, exist_ok=True)
        except Exception:
            pass

    def _base(self, frame_idx: int) -> str:
        return os.path.join(self.root_dir, f"gromacs_viewer_cache_f{frame_idx:06d}")

    def has_frame(self, frame_idx: int) -> bool:
        base = self._base(frame_idx)
        return (os.path.exists(base + "_v.npy") and
                os.path.exists(base + "_n.npy") and
                os.path.exists(base + "_c.npy"))

    def write_frame(self, frame_idx: int, vertices: np.ndarray, normals: np.ndarray, colors: np.ndarray) -> None:
        base = self._base(frame_idx)
        try:
            np.save(base + "_v.npy", vertices, allow_pickle=False)
            np.save(base + "_n.npy", normals, allow_pickle=False)
            np.save(base + "_c.npy", colors, allow_pickle=False)
        except Exception:
            # Best-effort; ignore write failures
            pass

    def read_frame(self, frame_idx: int):
        base = self._base(frame_idx)
        try:
            v = np.load(base + "_v.npy", allow_pickle=False)
            n = np.load(base + "_n.npy", allow_pickle=False)
            c = np.load(base + "_c.npy", allow_pickle=False)
            return v, n, c
        except Exception:
            return None


def _cache_root_dir() -> str:
    # Use the directory of this script as the cache root
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        script_dir = os.getcwd()
    return script_dir


# Default geometry parameters (mirror MDViewer3D defaults)
_SS_COLORS = {
    'H': (0.95, 0.15, 0.15),
    'E': (1.0, 0.85, 0.0),
    'C': (0.25, 0.45, 1.0)
}
_HELIX_WIDTH = 2.2
_HELIX_THICKNESS = 0.6
_HELIX_TWIST_DEG = 100.0
_HELIX_REF_STEP_LEN = 3.8
_SHEET_WIDTH = 2.4
_SHEET_THICKNESS_RATIO = 0.28
_LOOP_WIDTH = 1.0
_ARROW_LENGTH = 3.5
_TUBE_SEGMENTS = 16
_RIBBON_SMOOTH_SEGMENTS = 8


def compute_backbone_indices_from_template(template_atoms: List["Atom"]) -> List[int]:
    indices = [i for i, a in enumerate(template_atoms) if a.is_protein and a.atom_name.upper() == 'CA']
    if not indices:
        indices = [i for i, a in enumerate(template_atoms) if a.is_protein and a.atom_name.upper() in ('N', 'C')]
    if not indices:
        indices = [i for i, a in enumerate(template_atoms) if a.is_nucleic and a.atom_name.upper() in ('P', "C3'")]
    return indices


def _assign_secondary_structure_from_geometry_ext(backbone_indices: List[int], positions) -> List[str]:
    ss: List[str] = []
    if not backbone_indices or positions is None:
        return ss
    try:
        pos = positions
    except Exception:
        return ss
    pts = []
    for i in backbone_indices:
        if i < len(pos):
            pts.append(np.array(pos[i], dtype=np.float32))
    n = len(pts)
    if n < 6:
        return ['C'] * n

    ss = ['C'] * n
    helix_votes = [0] * n
    for i in range(0, n - 4):
        d3 = float(np.linalg.norm(pts[i] - pts[i + 3]))
        d4 = float(np.linalg.norm(pts[i] - pts[i + 4])) if i + 4 < n else 0.0
        if 4.5 <= d3 <= 6.0 and (i + 4 >= n or 5.0 <= d4 <= 6.8):
            for k in range(i, min(n, i + 5)):
                helix_votes[k] += 1

    turn_angles = [0.0] * n
    for i in range(1, n - 1):
        v1 = pts[i] - pts[i - 1]
        v2 = pts[i + 1] - pts[i]
        a1 = float(np.linalg.norm(v1))
        a2 = float(np.linalg.norm(v2))
        if a1 < 1e-5 or a2 < 1e-5:
            turn_angles[i] = 0.0
        else:
            cosang = float(np.dot(v1, v2) / (a1 * a2))
            cosang = max(-1.0, min(1.0, cosang))
            turn_angles[i] = math.acos(cosang)

    for i in range(n):
        if helix_votes[i] >= 1:
            ss[i] = 'H'

    i = 0
    while i < n:
        if ss[i] == 'H':
            j = i
            while j < n and ss[j] == 'H':
                j += 1
            if j - i < 3:
                for k in range(i, j):
                    ss[k] = 'C'
            else:
                up_ref = np.array([0.0, 0.0, 1.0], dtype=np.float32)
                N_prev = None
                phi_sum = 0.0
                for k in range(max(i, 1), min(j - 1, n - 1)):
                    v_prev = pts[k] - pts[k - 1]
                    v_next = pts[k + 1] - pts[k]
                    T = v_next + v_prev
                    tlen = float(np.linalg.norm(T))
                    if tlen < 1e-6:
                        continue
                    T = T / tlen
                    if N_prev is None:
                        base = up_ref
                        if abs(float(np.dot(T, base))) > 0.9:
                            base = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                        N_curr = base - np.dot(base, T) * T
                        nlen = float(np.linalg.norm(N_curr))
                        N_curr = N_curr / (nlen if nlen > 1e-6 else 1.0)
                    else:
                        N_curr = N_prev - np.dot(N_prev, T) * T
                        nlen = float(np.linalg.norm(N_curr))
                        if nlen < 1e-6:
                            N_curr = up_ref - np.dot(up_ref, T) * T
                            nlen = float(np.linalg.norm(N_curr))
                        N_curr = N_curr / (nlen if nlen > 1e-6 else 1.0)
                    if N_prev is not None:
                        dotn = float(np.dot(N_prev, N_curr))
                        dotn = max(-1.0, min(1.0, dotn))
                        phi_sum += math.acos(dotn)
                    N_prev = N_curr
                if phi_sum < 2.6:
                    for k in range(i, j):
                        ss[k] = 'C'
            i = j
        else:
            i += 1

    linear_thr = 0.7
    linear_thr_high = 1.0
    min_len_arrow = 3
    i = 1
    while i < n - 1:
        if ss[i] == 'C' and turn_angles[i] <= linear_thr:
            j = i + 1
            slack_allowed = 0
            slack_used = 0
            while j < n - 1 and ss[j] == 'C':
                ang = turn_angles[j]
                if ang <= linear_thr:
                    j += 1
                    continue
                if ang <= linear_thr_high and slack_used < slack_allowed:
                    slack_used += 1
                    j += 1
                    continue
                break
            run_len = j - i
            if run_len >= min_len_arrow:
                avg_bend = sum(turn_angles[k] for k in range(i, j)) / max(1, run_len)
                if avg_bend <= 0.6:
                    for k in range(i, j):
                        ss[k] = 'E'
            i = j
        else:
            i += 1

    for i in range(1, n - 1):
        if ss[i] == 'C' and ss[i - 1] == 'E' and ss[i + 1] == 'E':
            ss[i] = 'E'
    for i in range(1, n - 1):
        if ss[i] == 'C':
            if ss[i - 1] == 'H' and ss[i + 1] == 'H':
                ss[i] = 'H'
            elif ss[i - 1] == 'E' and ss[i + 1] == 'E':
                ss[i] = 'E'
    return ss


def _smooth_polyline_ext(points: List[Tuple[float, float, float]], segments: int) -> List[Tuple[float, float, float]]:
    if segments <= 1 or len(points) < 4:
        return [tuple(map(float, p)) for p in points]
    pts = [np.array(p, dtype=np.float32) for p in points]
    out: List[Tuple[float, float, float]] = []
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i+1], pts[i+2], pts[i+3]
        for j in range(segments):
            t = j / float(segments)
            t2 = t * t
            t3 = t2 * t
            a = -0.5*t3 + t2 - 0.5*t
            b = 1.5*t3 - 2.5*t2 + 1.0
            c = -1.5*t3 + 2.0*t2 + 0.5*t
            d = 0.5*t3 - 0.5*t2
            pt = a*p0 + b*p1 + c*p2 + d*p3
            out.append((float(pt[0]), float(pt[1]), float(pt[2])))
    out.append(tuple(map(float, pts[-2])))
    out.append(tuple(map(float, pts[-1])))
    return out


def _contiguous_runs(labels: List[str]) -> List[Tuple[str, int, int]]:
    runs: List[Tuple[str, int, int]] = []
    if len(labels) < 2:
        return runs
    cur = labels[1]
    start = 1
    for i in range(2, len(labels) - 1):
        if labels[i] != cur:
            runs.append((cur, start, i))
            cur = labels[i]
            start = i
    runs.append((cur, start, len(labels) - 1))
    return runs


def _append_tri_list(tris: list, v1, n1, v2, n2, v3, n3, color, idx):
    tris.append((
        (float(v1[0]), float(v1[1]), float(v1[2])),
        (float(n1[0]), float(n1[1]), float(n1[2])),
        (float(v2[0]), float(v2[1]), float(v2[2])),
        (float(n2[0]), float(n2[1]), float(n2[2])),
        (float(v3[0]), float(v3[1]), float(v3[2])),
        (float(n3[0]), float(n3[1]), float(n3[2])),
        (float(color[0]), float(color[1]), float(color[2])),
        int(idx)
    ))


def _sweep_tube_ext(tris, centers, Ts, Ns, Bs, radius, color, base_idx):
    ring_slices = max(12, _TUBE_SEGMENTS)
    prev_ring = None
    # Try GPU to build rings
    used_gpu = False
    if _init_opencl_once():
        try:
            num = len(centers)
            if num > 0:
                centers_np = np.asarray(centers, dtype=np.float32)
                Ns_np = np.asarray(Ns, dtype=np.float32)
                Bs_np = np.asarray(Bs, dtype=np.float32)
                out_v = np.empty((num * ring_slices, 3), dtype=np.float32)
                out_n = np.empty((num * ring_slices, 3), dtype=np.float32)
                mf = cl.mem_flags
                centers_buf = cl.Buffer(_CL_CTX, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=centers_np)
                Ns_buf = cl.Buffer(_CL_CTX, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=Ns_np)
                Bs_buf = cl.Buffer(_CL_CTX, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=Bs_np)
                out_v_buf = cl.Buffer(_CL_CTX, mf.WRITE_ONLY, out_v.nbytes)
                out_n_buf = cl.Buffer(_CL_CTX, mf.WRITE_ONLY, out_n.nbytes)
                _CL_PROG.build_rings(_CL_QUEUE,
                                     (num * ring_slices,), None,
                                     centers_buf, Ns_buf, Bs_buf,
                                     np.float32(radius), np.int32(ring_slices), np.int32(num),
                                     out_v_buf, out_n_buf)
                cl.enqueue_copy(_CL_QUEUE, out_v, out_v_buf).wait()
                cl.enqueue_copy(_CL_QUEUE, out_n, out_n_buf).wait()
                # Convert rings per center
                rings = [out_v[i*ring_slices:(i+1)*ring_slices] for i in range(num)]
                norms = [out_n[i*ring_slices:(i+1)*ring_slices] for i in range(num)]
                for i in range(num):
                    ring = rings[i]
                    c = centers[i]
                    if prev_ring is not None:
                        for k in range(ring_slices):
                            k0 = k
                            k1 = (k + 1) % ring_slices
                            v00 = prev_ring[k0]
                            v01 = prev_ring[k1]
                            v10 = ring[k0]
                            v11 = ring[k1]
                            n10 = norms[i][k0]
                            n11 = norms[i][k1]
                            n00 = n10
                            n01 = n11
                            _append_tri_list(tris, v00, n00, v10, n10, v11, n11, color, base_idx + i)
                            _append_tri_list(tris, v00, n00, v11, n11, v01, n01, color, base_idx + i)
                    prev_ring = ring
                used_gpu = True
        except Exception:
            used_gpu = False
    if used_gpu:
        return
    # CPU fallback
    for i in range(len(centers)):
        c = centers[i]
        N = Ns[i]
        B = Bs[i]
        ring = []
        for k in range(ring_slices):
            theta = (2.0 * math.pi * k) / ring_slices
            off = math.cos(theta) * N * radius + math.sin(theta) * B * radius
            ring.append(c + off)
        if prev_ring is not None:
            for k in range(ring_slices):
                k0 = k
                k1 = (k + 1) % ring_slices
                v00 = prev_ring[k0]
                v01 = prev_ring[k1]
                v10 = ring[k0]
                v11 = ring[k1]
                n10 = (v10 - c)
                n10 = n10 / (np.linalg.norm(n10) if np.linalg.norm(n10) > 1e-6 else 1.0)
                n11 = (v11 - c)
                n11 = n11 / (np.linalg.norm(n11) if np.linalg.norm(n11) > 1e-6 else 1.0)
                n00 = n10
                n01 = n11
                _append_tri_list(tris, v00, n00, v10, n10, v11, n11, color, base_idx + i)
                _append_tri_list(tris, v00, n00, v11, n11, v01, n01, color, base_idx + i)
        prev_ring = ring


def _sweep_sheet_ext(tris, centers, Ts, Ns, Bs, width, thickness, color, add_arrow, base_idx):
    half = width * 0.5
    prev = None
    for i in range(len(centers)):
        c = centers[i]
        T = Ts[i]
        N = Ns[i]
        B = Bs[i]
        if prev is not None:
            _, _, _, _, pN, pB, pT, pc = prev
            if np.dot(N, pN) < 0:
                N = -N
                B = -B
        left = c - N * half
        right = c + N * half
        top_left = left + B * (thickness * 0.5)
        top_right = right + B * (thickness * 0.5)
        bot_left = left - B * (thickness * 0.5)
        bot_right = right - B * (thickness * 0.5)
        frame = (top_left, top_right, bot_left, bot_right, N, B, T, c)
        if prev is not None:
            p_tl, p_tr, p_bl, p_br, pN, pB, pT, pc = prev
            _append_tri_list(tris, p_tl, pN, top_left, N, top_right, N, color, base_idx + i)
            _append_tri_list(tris, p_tl, pN, top_right, N, p_tr, pN, color, base_idx + i)
            _append_tri_list(tris, p_bl, -pN, bot_right, -N, bot_left, -N, color, base_idx + i)
            _append_tri_list(tris, p_bl, -pN, p_br, -pN, bot_right, -N, color, base_idx + i)
            _append_tri_list(tris, p_tr, pB, top_right, B, bot_right, -B, color, base_idx + i)
            _append_tri_list(tris, p_tr, pB, bot_right, -B, p_br, -pB, color, base_idx + i)
        prev = frame

    if add_arrow and prev is not None and len(centers) >= 2:
        p_tl, p_tr, p_bl, p_br, pN, pB, pT, pc = prev
        if np.linalg.norm(pT) < 1e-6:
            return
        tip_center = pc + pT * _ARROW_LENGTH
        tip_top = tip_center + pB * (thickness * 0.5)
        tip_bot = tip_center - pB * (thickness * 0.5)
        widen = 1.15
        tl = p_tl + (p_tl - pc) * (widen - 1.0)
        tr = p_tr + (p_tr - pc) * (widen - 1.0)
        bl = p_bl + (p_bl - pc) * (widen - 1.0)
        br = p_br + (p_br - pc) * (widen - 1.0)
        _append_tri_list(tris, tl, pN, tr, pN, tip_top, pN, color, base_idx + len(centers))
        _append_tri_list(tris, bl, -pN, tip_bot, -pN, br, -pN, color, base_idx + len(centers))
        _append_tri_list(tris, bl, -pB, tip_bot, -pB, tip_top, pB, color, base_idx + len(centers))
        _append_tri_list(tris, bl, -pB, tip_top, pB, tl, pB, color, base_idx + len(centers))
        _append_tri_list(tris, tr, pB, tip_top, pB, tip_bot, -pB, color, base_idx + len(centers))
        _append_tri_list(tris, tr, pB, tip_bot, -pB, br, -pB, color, base_idx + len(centers))


def _build_TNB_for_points(points: List[Tuple[float, float, float]]):
    pts = [np.array(p, dtype=np.float32) for p in points]
    n = len(pts)
    up_ref = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    T_list: List[np.ndarray] = [None] * n  # type: ignore
    N_list: List[np.ndarray] = [None] * n  # type: ignore
    B_list: List[np.ndarray] = [None] * n  # type: ignore
    prev_T = None
    prev_N = None
    for i in range(1, n - 1):
        p_prev = np.array(pts[i - 1], dtype=np.float32)
        p_curr = np.array(pts[i], dtype=np.float32)
        p_next = np.array(pts[i + 1], dtype=np.float32)
        T = p_next - p_prev
        norm = np.linalg.norm(T)
        if norm < 1e-6:
            T = prev_T if prev_T is not None else np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            T = T / norm
        if prev_N is None:
            base = up_ref
            if abs(np.dot(T, base)) > 0.9:
                base = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            N = base - np.dot(base, T) * T
            nlen = np.linalg.norm(N)
            N = N / (nlen if nlen > 1e-6 else 1.0)
        else:
            N = prev_N - np.dot(prev_N, T) * T
            nlen = np.linalg.norm(N)
            if nlen < 1e-6:
                N = up_ref - np.dot(up_ref, T) * T
                nlen = np.linalg.norm(N)
            N = N / (nlen if nlen > 1e-6 else 1.0)
        B = np.cross(T, N)
        blen = np.linalg.norm(B)
        if blen > 1e-6:
            B = B / blen
        T_list[i] = T
        N_list[i] = N
        B_list[i] = B
        prev_T = T
        prev_N = N
    return pts, T_list, N_list, B_list


def _sweep_helix_ribbon_ext(tris, centers, Ts, Ns, Bs, width, thickness, twist_deg_per_step, color, base_idx):
    half = width * 0.5
    prev = None
    current_rot_deg = 0.0
    prevN = None
    for i in range(len(centers)):
        c = centers[i]
        T = Ts[i]
        N = Ns[i]
        B = Bs[i]
        if prevN is not None and np.dot(N, prevN) < 0:
            N = -N
            B = -B
        prevN = N
        angle = math.radians(current_rot_deg)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        N_rot = N * cos_a + B * sin_a
        B_rot = -N * sin_a + B * cos_a
        left = c - N_rot * half
        right = c + N_rot * half
        top_left = left + B_rot * (thickness * 0.5)
        top_right = right + B_rot * (thickness * 0.5)
        bot_left = left - B_rot * (thickness * 0.5)
        bot_right = right - B_rot * (thickness * 0.5)
        frame = (top_left, top_right, bot_left, bot_right, N_rot, B_rot, T, c)
        if prev is not None:
            p_tl, p_tr, p_bl, p_br, pN, pB, pT, pc = prev
            _append_tri_list(tris, p_tl, pN, top_left, N_rot, top_right, N_rot, color, base_idx + i)
            _append_tri_list(tris, p_tl, pN, top_right, N_rot, p_tr, pN, color, base_idx + i)
            _append_tri_list(tris, p_bl, -pN, bot_right, -N_rot, bot_left, -N_rot, color, base_idx + i)
            _append_tri_list(tris, p_bl, -pN, p_br, -pN, bot_right, -N_rot, color, base_idx + i)
            _append_tri_list(tris, p_bl, -pB, bot_left, -B_rot, top_left, B_rot, color, base_idx + i)
            _append_tri_list(tris, p_bl, -pB, top_left, B_rot, p_tl, pB, color, base_idx + i)
            _append_tri_list(tris, p_tr, pB, top_right, B_rot, bot_right, -B_rot, color, base_idx + i)
            _append_tri_list(tris, p_tr, pB, bot_right, -B_rot, p_br, -pB, color, base_idx + i)
        prev = frame
        current_rot_deg += twist_deg_per_step


def compute_cartoon_arrays_for_frame(template_atoms: List["Atom"], positions, backbone_indices: List[int], precomputed_ss: Optional[List[str]] = None):
    # Build backbone points list
    N = len(positions)
    pts = [(float(positions[i][0]), float(positions[i][1]), float(positions[i][2]))
           for i in backbone_indices if i < N]
    if len(pts) < 3:
        return None
    # Smooth backbone
    pts = _smooth_polyline_ext(pts, max(4, _RIBBON_SMOOTH_SEGMENTS))
    if len(pts) < 3:
        return None
    # Assign SS: prefer precomputed from reference frame if provided
    ss = precomputed_ss if precomputed_ss is not None else _assign_secondary_structure_from_geometry_ext(backbone_indices, positions)
    # Resample labels to length of smoothed points
    if not ss:
        ss = ['C'] * len(pts)
    else:
        if len(ss) != len(pts):
            scaled = []
            for i in range(len(pts)):
                j = int(i * (len(ss) - 1) / max(1, len(pts) - 1))
                scaled.append(ss[min(j, len(ss)-1)])
            ss = scaled

    # Build frames
    _, T_list, N_list, B_list = _build_TNB_for_points(pts)
    runs = _contiguous_runs(ss)
    if not runs:
        return None
    tris = []
    for mode, s, e in runs:
        centers = [np.array(pts[k], dtype=np.float32) for k in range(s, e)]
        Ts = [T_list[k] for k in range(s, e)]
        Ns = [N_list[k] for k in range(s, e)]
        Bs = [B_list[k] for k in range(s, e)]
        valid = [i for i in range(len(centers)) if Ts[i] is not None and Ns[i] is not None and Bs[i] is not None]
        if len(valid) < 2:
            continue
        centers = [centers[i] for i in valid]
        Ts = [Ts[i] for i in valid]
        Ns = [Ns[i] for i in valid]
        Bs = [Bs[i] for i in valid]
        base_idx = s
        if mode == 'H':
            color = _SS_COLORS['H']
            step_lengths = []
            for i2 in range(1, len(centers)):
                step_lengths.append(float(np.linalg.norm(centers[i2] - centers[i2 - 1])))
            avg_step = max(1e-3, (sum(step_lengths) / len(step_lengths)) if step_lengths else _HELIX_REF_STEP_LEN)
            twist_per_step = _HELIX_TWIST_DEG * (avg_step / _HELIX_REF_STEP_LEN)
            thickness = _HELIX_THICKNESS
            width = _HELIX_WIDTH
            _sweep_helix_ribbon_ext(tris, centers, Ts, Ns, Bs, width, thickness, twist_per_step, color, base_idx)
        elif mode == 'E':
            color = _SS_COLORS['E']
            sheet_thickness = max(0.5, _SHEET_WIDTH * _SHEET_THICKNESS_RATIO)
            _sweep_sheet_ext(tris, centers, Ts, Ns, Bs, _SHEET_WIDTH, sheet_thickness, color, add_arrow=True, base_idx=base_idx)
        else:
            color = _SS_COLORS['C']
            loop_radius = max(0.8, _LOOP_WIDTH * 0.6)
            _sweep_tube_ext(tris, centers, Ts, Ns, Bs, loop_radius, color, base_idx)

    if not tris:
        return None
    num = len(tris)
    v = np.empty((num * 3, 3), dtype=np.float32)
    n = np.empty((num * 3, 3), dtype=np.float32)
    c = np.empty((num * 3, 3), dtype=np.float32)
    idx = 0
    for (v1, n1, v2, n2, v3, n3, col, _) in tris:
        v[idx] = v1; n[idx] = n1; c[idx] = col; idx += 1
        v[idx] = v2; n[idx] = n2; c[idx] = col; idx += 1
        v[idx] = v3; n[idx] = n3; c[idx] = col; idx += 1
    return v, n, c


def precompute_cartoon_geometry(provider: BaseTrajectoryProvider,
                                template_atoms: List["Atom"],
                                gro_path: Optional[str],
                                xtc_path: Optional[str],
                                progress_cb=None) -> str:
    """Precompute cartoon geometry for all frames and store on disk. Returns directory path."""
    total = getattr(provider, 'get_num_frames', lambda: 1)()
    # Use 'cartoon' folder next to this script as cache directory
    out_dir = get_subdir('gromacs_viewer_cache')
    store = PrecomputedCartoonStore(out_dir)
    backbone_indices = compute_backbone_indices_from_template(template_atoms)
    if not backbone_indices:
        # Nothing to precompute
        return out_dir

    # Use a small worker pool for CPU-bound geometry
    max_workers = max(2, min(8, (os.cpu_count() or 4)))
    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = []

    completed = 0
    # Sequentially fetch frames (MDAnalysis is not thread-safe), compute geometry in background
    for fidx in range(total):
        # If cache exists for this frame, skip computation
        if store.has_frame(fidx):
            completed += 1
            if progress_cb:
                progress_cb(completed, total)
            continue
        try:
            pos = provider.get_positions(fidx)
        except Exception:
            pos = None
        if pos is None:
            # emit progress anyway
            completed += 1
            if progress_cb:
                progress_cb(completed, total)
            continue
        # Submit compute task
        def _task(frame_index: int, positions):
            try:
                res = compute_cartoon_arrays_for_frame(template_atoms, positions, backbone_indices)
                if res is not None:
                    v, n, c = res
                    store.write_frame(frame_index, v, n, c)
            except Exception:
                pass
            return frame_index
        futures.append(executor.submit(_task, fidx, np.asarray(pos, dtype=np.float32)))
        # Drain finished futures to update progress
        done_now = []
        for fut in futures:
            if fut.done():
                done_now.append(fut)
        for fut in done_now:
            futures.remove(fut)
            try:
                _ = fut.result()
            except Exception:
                pass
            completed += 1
            if progress_cb:
                progress_cb(completed, total)

    # Wait remaining
    for fut in as_completed(futures):
        try:
            _ = fut.result()
        except Exception:
            pass
        completed += 1
        if progress_cb:
            progress_cb(completed, total)
    executor.shutdown(wait=True)
    return out_dir

class RenderWorker(QThread):
    """Worker thread for heavy rendering calculations"""
    frame_ready = Signal(int, list)  # frame_index, display_data
    frame_positions_ready = Signal(int, list)  # frame_index, positions (list of (x,y,z))
    precompute_progress = Signal(int)  # 0..100
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_frame = 0
        self.mutex = QMutex()
        self.should_update = False
        self.provider = None
        self.template_atoms: List[Atom] = []
        self.selection_mask: Optional[List[bool]] = None
        # Playback prefetch
        self.playing = False
        self.prefetch_cache = {}
        self.max_prefetch = 12
        self.prefetch_target = 12
        self._last_frame = -1
        # Precompute management
        self._precompute_dir: Optional[str] = None
        self._precompute_total = 0
        self._precompute_done = 0
        
    def set_provider(self, provider, template_atoms: List[Atom]):
        with QMutexLocker(self.mutex):
            self.provider = provider
            self.template_atoms = template_atoms
            self.should_update = True
            # reset precompute counters when provider changes
            self._precompute_dir = None
            self._precompute_total = 0
            self._precompute_done = 0
    
    def set_current_frame(self, frame_idx: int):
        with QMutexLocker(self.mutex):
            # If jump is large or backward, clear cache to avoid stale prefetch
            if abs(frame_idx - self.current_frame) > 2:
                self.prefetch_cache.clear()
            self.current_frame = frame_idx
            self.should_update = True
    
    def set_selection_mask(self, mask: List[bool]):
        with QMutexLocker(self.mutex):
            self.selection_mask = mask
            self.prefetch_cache.clear()
            self.should_update = True

    def set_playing(self, playing: bool):
        with QMutexLocker(self.mutex):
            self.playing = playing
            if not playing:
                # Keep only the current frame cached
                cf = self.current_frame
                self.prefetch_cache = {k: v for (k, v) in self.prefetch_cache.items() if k == cf}
            self.should_update = True

    def set_prefetch_target(self, n: int):
        with QMutexLocker(self.mutex):
            self.prefetch_target = max(1, int(n))
            self.max_prefetch = max(12, min(self.prefetch_target, self.prefetch_target))

    def set_precompute_dir(self, directory: Optional[str]):
        with QMutexLocker(self.mutex):
            self._precompute_dir = directory
    
    def run(self):
        while not self.isInterruptionRequested():
            should_process = False
            with QMutexLocker(self.mutex):
                should_process = self.should_update
                self.should_update = False
                
            if should_process and self.provider is not None and self.template_atoms:
                try:
                    # Use prefetched positions when available
                    if self.current_frame in self.prefetch_cache:
                        positions_np = self.prefetch_cache.pop(self.current_frame)
                    else:
                        p = self.provider.get_positions(self.current_frame)
                        positions_np = np.asarray(p, dtype=np.float32)
                    npos = len(positions_np)
                    natoms = min(len(self.template_atoms), npos)
                    # Build display data using selection mask if provided
                    display_data = []
                    if self.selection_mask is not None:
                        for i, m in enumerate(self.selection_mask[:natoms]):
                            if not m:
                                continue
                            atom_template = self.template_atoms[i]
                            pos = positions_np[i]
                            display_data.append({
                                'position': (float(pos[0]), float(pos[1]), float(pos[2])),
                                'color': atom_template.color,
                                'radius': atom_template.radius,
                                'is_protein': atom_template.is_protein
                            })
                    # Emit positions cache first
                    self.frame_positions_ready.emit(self.current_frame, positions_np)
                    self.frame_ready.emit(self.current_frame, display_data)
                except Exception:
                    pass
            # Background prefetch of next frames during playback
            try:
                do_prefetch = False
                with QMutexLocker(self.mutex):
                    do_prefetch = self.playing and (self.provider is not None)
                    start = self.current_frame + 1
                    end = min(start + self.prefetch_target, getattr(self.provider, 'get_num_frames', lambda: start)( ))
                if do_prefetch:
                    # Prefetch aggressively to fill at least half of frames
                    for fidx in range(start, end):
                        if fidx in self.prefetch_cache:
                            continue
                        try:
                            p = self.provider.get_positions(fidx)
                            positions_np = np.asarray(p, dtype=np.float32)
                            self.prefetch_cache[fidx] = positions_np
                        except Exception:
                            break
                    # Trim cache size to target window
                    keys = sorted(self.prefetch_cache.keys())
                    while len(keys) > self.prefetch_target:
                        k = keys.pop(0)
                        self.prefetch_cache.pop(k, None)
            except Exception:
                pass
            
            self.msleep(16)  # ~60 FPS

class MDViewer3D(QtOpenGLWidgets.QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.display_data = []
        self.camera_distance = 50.0
        self.camera_rotation_x = 0.0
        self.camera_rotation_y = 0.0
        self.last_mouse_pos = None
        
        # Display options
        self.show_atoms = False
        self.show_bonds = False
        self.atom_scale = 1.0
        self.render_mode = 'Auto'  # Auto, Spheres, Points
        self.point_size = 3
        self.ambient = 0.25
        self.diffuse = 0.75
        self.specular = 0.25
        self.shininess = 32.0
        self.protein_atom_scale = 1.5
        # Cartoon options
        self.cartoon_enabled = False
        self.cartoon_radius = 0.6
        self.cartoon_color = (0.9, 0.9, 0.2)
        self._provider = None
        self._template_atoms: List[Atom] = []
        self._backbone_indices: List[int] = []
        self._current_frame_idx: int = 0
        # Ribbon options
        self.ribbon_enabled = True
        self.ribbon_width = 1.2
        self.ribbon_twist_deg = 100.0
        self.ribbon_smooth_segments = 8
        # Cartoon tube options
        self.tube_segments = 16  # ring resolution
        self.tube_step = 1       # subsample along spline for speed
        self.selection_mask: Optional[List[bool]] = None
        # Secondary structure cartoon parameters (enhanced thickness and colors)
        self.helix_radius = 1.2
        self.sheet_width = 2.4
        self.loop_width = 1.0
        self.arrow_tip_scale = 1.8
        self.arrow_length = 3.5
        self.ss_colors = {
            'H': (0.95, 0.15, 0.15),  # helix red (strong)
            'E': (1.0, 0.85, 0.0),    # sheet yellow (strong)
            'C': (0.25, 0.45, 1.0)    # loop blue (distinct)
        }
        # Helix ribbon parameters
        self.helix_width = 2.2
        self.helix_thickness = 0.6
        self.helix_twist_deg = 100.0  # approx alpha-helix twist per residue
        self.helix_ref_step_len = 3.8  # reference backbone step length (A) to scale twist per-residue
        # Ligand highlight for DCK
        self.ligand_highlight_resnames = {'UNL'}
        self.ligand_highlight_color = (1.0, 0.5, 0.0)
        self.ligand_highlight_atom_scale = 0.75
        self.ligand_highlight_stick_radius = 0.2
        # Cached cartoon mesh (to avoid heavy recompute every frame)
        self._cartoon_cache_valid = False
        self._cartoon_triangles = []  # list of (v1, n1, v2, n2, v3, n3, color, orig_idx)
        self._cartoon_cached_frame_idx = -1
        self._cartoon_cached_sel_key: Optional[tuple] = None
        # Client-side arrays cache for cartoon triangles
        self._cartoon_vertices = None
        self._cartoon_normals = None
        self._cartoon_colors = None
        self._cartoon_arrays_version = 0
        self._cartoon_arrays_built_for_version = -1
        self.cartoon_auto_rebuild = False
        # Ligand/Water rendering options
        self.water_color = (0.35, 0.6, 1.0)
        self.water_point_size = 2
        self.ligand_atom_scale = 0.6
        self.stick_radius = 0.15
        self.ligand_bond_slices = 10
        self.bond_color = (0.8, 0.8, 0.8)
        self._water_o_indices = []
        self._ligand_groups = {}
        self._ligand_bonds = {}
        
        # Performance options
        self.sphere_quality = 12  # Lower for better performance
        # Reusable GLU quadrics
        self._sphere_quadric = None
        self._cylinder_quadric = None
        
        self.setMinimumSize(800, 600)
        
        # Setup render worker
        self.render_worker = RenderWorker()
        self.render_worker.frame_ready.connect(self.update_display_data)
        # Receive per-frame positions to avoid extra provider calls during playback
        self.render_worker.frame_positions_ready.connect(self._on_worker_positions)
        self.render_worker.start()
        # Positions cache updated each frame by worker for smooth playback
        self._positions_cache_frame = -1
        self._positions_cache = None  # np.ndarray float32 (N,3)
        # On-disk precompute cache for cartoons (filled by loader thread)
        self._precompute_dir: Optional[str] = None
    
    def set_frames(self, frames: List[Frame]):
        # Backward compatibility: wrap frames in preloaded provider
        self.render_worker.set_provider(_PreloadedProvider(frames), frames[0].atoms if frames else [])
        self.set_provider(_PreloadedProvider(frames), frames[0].atoms if frames else [])
    
    def set_current_frame(self, frame_idx: int):
        self.render_worker.set_current_frame(frame_idx)
        self._current_frame_idx = frame_idx
        if self.cartoon_auto_rebuild:
            self._cartoon_cache_valid = False
    
    def set_provider(self, provider, template_atoms: List[Atom]):
        self._provider = provider
        self._template_atoms = template_atoms or []
        # Compute protein backbone indices (C-alpha). If none, try N, C as fallback; for nucleic acids, P/C3'.
        self._backbone_indices = [i for i, a in enumerate(self._template_atoms) if a.is_protein and a.atom_name.upper() == 'CA']
        if not self._backbone_indices:
            self._backbone_indices = [i for i, a in enumerate(self._template_atoms) if a.is_protein and a.atom_name.upper() in ('N', 'C')]
        if not self._backbone_indices:
            self._backbone_indices = [i for i, a in enumerate(self._template_atoms) if a.is_nucleic and a.atom_name.upper() in ('P', "C3'")]
        # Prepare water oxygen indices
        self._water_o_indices = [i for i, a in enumerate(self._template_atoms) if a.is_water and (a.atom_name.upper().startswith('O') or a.element.upper() == 'O')]
        # Prepare ligand groups and bonds
        self._build_ligand_groups_and_bonds()
        # Precompute naive secondary structure along backbone (H helix, E sheet, C coil)
        self._ss_assignments = self._assign_secondary_structure_from_geometry(self._backbone_indices)
        if not self._ss_assignments and self._backbone_indices:
            # If geometry-based assignment failed, default to coil of proper length
            try:
                n = len(self._backbone_indices)
                self._ss_assignments = ['C'] * n
            except Exception:
                self._ss_assignments = []
        self._cartoon_cache_valid = False
        # If we have precomputed geometry, try to use it during paintGL
        try:
            # Build expected dir from current loader state if available through parent window
            # The main window sets this via set_precompute_dir
            pass
        except Exception:
            pass

    def set_precompute_dir(self, directory: Optional[str]):
        self._precompute_dir = directory

    def _assign_secondary_structure_from_geometry(self, backbone_indices: List[int]):
        # Geometry-based heuristic with CA-spacing signatures (robust helix detection):
        # - Alpha-helix: |r_i - r_{i+3}| ≈ 5.2±0.7 Å, |r_i - r_{i+4}| ≈ 6.0±0.8 Å
        # - Beta/extended: large turn angles, |r_i - r_{i+2}| ≈ 6.8±1.2 Å, vectors alternate
        ss: List[str] = []
        if not backbone_indices or not self._provider:
            return ss
        try:
            pos = self._provider.get_positions(self._current_frame_idx)
        except Exception:
            return ss
        pts = []
        for i in backbone_indices:
            if i < len(pos):
                pts.append(np.array(pos[i], dtype=np.float32))
        n = len(pts)
        if n < 6:
            return ['C'] * n

        ss = ['C'] * n
        helix_votes = [0] * n

        # Vote helix by i..i+3 window distances
        for i in range(0, n - 4):
            d3 = float(np.linalg.norm(pts[i] - pts[i + 3]))
            d4 = float(np.linalg.norm(pts[i] - pts[i + 4])) if i + 4 < n else 0.0
            if 4.5 <= d3 <= 6.0 and (i + 4 >= n or 5.0 <= d4 <= 6.8):
                # vote for residues spanning this window
                for k in range(i, min(n, i + 5)):
                    helix_votes[k] += 1

        # Precompute local turning angle (0 = straight)
        turn_angles = [0.0] * n
        for i in range(1, n - 1):
            v1 = pts[i] - pts[i - 1]
            v2 = pts[i + 1] - pts[i]
            a1 = float(np.linalg.norm(v1))
            a2 = float(np.linalg.norm(v2))
            if a1 < 1e-5 or a2 < 1e-5:
                turn_angles[i] = 0.0
            else:
                cosang = float(np.dot(v1, v2) / (a1 * a2))
                cosang = max(-1.0, min(1.0, cosang))
                turn_angles[i] = math.acos(cosang)

        # Assign based on helix votes with thresholds and minimal segment lengths
        for i in range(n):
            if helix_votes[i] >= 1:
                ss[i] = 'H'
        # Build contiguous helix segments and filter short ones (<4)
        i = 0
        while i < n:
            if ss[i] == 'H':
                j = i
                while j < n and ss[j] == 'H':
                    j += 1
                if j - i < 3:
                    for k in range(i, j):
                        ss[k] = 'C'
                else:
                    # Validate helix by cumulative frame twist across the run
                    # Build T/N using simple parallel transport on this run
                    # Initialize N from global up and re-project
                    up_ref = np.array([0.0, 0.0, 1.0], dtype=np.float32)
                    N_prev = None
                    phi_sum = 0.0
                    for k in range(max(i, 1), min(j - 1, n - 1)):
                        v_prev = pts[k] - pts[k - 1]
                        v_next = pts[k + 1] - pts[k]
                        T = v_next + v_prev
                        tlen = float(np.linalg.norm(T))
                        if tlen < 1e-6:
                            continue
                        T = T / tlen
                        if N_prev is None:
                            base = up_ref
                            if abs(float(np.dot(T, base))) > 0.9:
                                base = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                            N_curr = base - np.dot(base, T) * T
                            nlen = float(np.linalg.norm(N_curr))
                            N_curr = N_curr / (nlen if nlen > 1e-6 else 1.0)
                        else:
                            N_curr = N_prev - np.dot(N_prev, T) * T
                            nlen = float(np.linalg.norm(N_curr))
                            if nlen < 1e-6:
                                N_curr = up_ref - np.dot(up_ref, T) * T
                                nlen = float(np.linalg.norm(N_curr))
                            N_curr = N_curr / (nlen if nlen > 1e-6 else 1.0)
                        if N_prev is not None:
                            dotn = float(np.dot(N_prev, N_curr))
                            dotn = max(-1.0, min(1.0, dotn))
                            phi_sum += math.acos(dotn)
                        N_prev = N_curr
                    # Require moderate accumulated twist to keep helix (allow short 1-turn helix)
                    if phi_sum < 2.6:
                        for k in range(i, j):
                            ss[k] = 'C'
                i = j
            else:
                i += 1

        # Now assign sheets (arrow) where not helix: long, near-straight segments (lower sensitivity)
        # Turunkan sensitivitas agar tidak “mengambil” helix yang tidak sempurna
        linear_thr = 0.7   # rad ~40 deg primary threshold
        linear_thr_high = 1.0  # rad ~57 deg occasional allowance within a run
        min_len_arrow = 3
        i = 1
        while i < n - 1:
            if ss[i] == 'C' and turn_angles[i] <= linear_thr:
                j = i + 1
                slack_allowed = 0  # do not allow large bends within an arrow run
                slack_used = 0
                while j < n - 1 and ss[j] == 'C':
                    ang = turn_angles[j]
                    if ang <= linear_thr:
                        j += 1
                        continue
                    if ang <= linear_thr_high and slack_used < slack_allowed:
                        slack_used += 1
                        j += 1
                        continue
                    break
                run_len = j - i
                if run_len >= min_len_arrow:
                    # Optional: ensure average bend is small
                    avg_bend = sum(turn_angles[k] for k in range(i, j)) / max(1, run_len)
                    if avg_bend <= 0.6:
                        for k in range(i, j):
                            ss[k] = 'E'
                i = j
            else:
                i += 1

        # Fill single-residue gaps inside arrow runs: E C E -> E E E
        for i in range(1, n - 1):
            if ss[i] == 'C' and ss[i - 1] == 'E' and ss[i + 1] == 'E':
                ss[i] = 'E'

        # Gentle expansion at segment borders (1-residue pad)
        for i in range(1, n - 1):
            if ss[i] == 'C':
                if ss[i - 1] == 'H' and ss[i + 1] == 'H':
                    ss[i] = 'H'
                elif ss[i - 1] == 'E' and ss[i + 1] == 'E':
                    ss[i] = 'E'
        return ss

    def set_selection_mask(self, mask: List[bool]):
        self.selection_mask = mask
        self._cartoon_cache_valid = False
        self.update()

    def _build_ligand_groups_and_bonds(self):
        self._ligand_groups = {}
        self._ligand_bonds = {}
        if not self._template_atoms:
            return
        # Build mapping from residue key to atom indices (all non-protein, non-water)
        for idx, atom in enumerate(self._template_atoms):
            is_ball_and_stick = (not atom.is_protein and not atom.is_water)
            if not is_ball_and_stick:
                continue
            key = (atom.chain, atom.residue_id, atom.residue_name)
            if key not in self._ligand_groups:
                self._ligand_groups[key] = []
            self._ligand_groups[key].append(idx)
        # Infer bonds per ligand group using template positions
        template_positions = [(a.x, a.y, a.z) for a in self._template_atoms]
        for key, indices in self._ligand_groups.items():
            pairs = self._infer_bonds_for_indices(indices, template_positions)
            self._ligand_bonds[key] = pairs

    def _infer_bonds_for_indices(self, indices: List[int], positions: List[Tuple[float, float, float]]):
        pairs: List[Tuple[int, int]] = []
        if len(indices) <= 1:
            return pairs
        # Simple O(n^2) within residue; acceptable for small ligands
        for i_local in range(len(indices)):
            i_idx = indices[i_local]
            a_i = self._template_atoms[i_idx]
            e_i = a_i.element.upper()
            r_i = COVALENT_RADII.get(e_i, 0.77)
            xi, yi, zi = positions[i_idx]
            for j_local in range(i_local + 1, len(indices)):
                j_idx = indices[j_local]
                a_j = self._template_atoms[j_idx]
                e_j = a_j.element.upper()
                r_j = COVALENT_RADII.get(e_j, 0.77)
                xj, yj, zj = positions[j_idx]
                dx = xi - xj
                dy = yi - yj
                dz = zi - zj
                d2 = dx*dx + dy*dy + dz*dz
                # Bond threshold with tolerance
                threshold = r_i + r_j + 0.45
                if d2 <= threshold * threshold:
                    # Skip unlikely H-H bonds
                    if e_i == 'H' and e_j == 'H':
                        continue
                    pairs.append((i_idx, j_idx))
        return pairs
    
    def update_display_data(self, frame_idx: int, display_data: list):
        self.display_data = display_data
        self.update()

    def _on_worker_positions(self, frame_idx: int, positions):
        # Cache positions for this frame so paintGL can reuse without provider calls
        self._positions_cache_frame = frame_idx
        try:
            # ensure numpy float32
            self._positions_cache = positions if isinstance(positions, np.ndarray) else np.asarray(positions, dtype=np.float32)
        except Exception:
            self._positions_cache = None
    
    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_NORMALIZE)
        glShadeModel(GL_SMOOTH)
        # Enable face culling for fewer fragments
        glEnable(GL_CULL_FACE)
        
        # Set up lighting
        glLightfv(GL_LIGHT0, GL_POSITION, [0.2, 0.5, 1.0, 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [self.ambient, self.ambient, self.ambient, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [self.diffuse, self.diffuse, self.diffuse, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [self.specular, self.specular, self.specular, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, self.shininess)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [self.specular, self.specular, self.specular, 1.0])
        
        glClearColor(0.0, 0.0, 0.0, 1.0)
        # Create reusable quadrics
        try:
            self._sphere_quadric = gluNewQuadric()
            gluQuadricNormals(self._sphere_quadric, GLU_SMOOTH)
            self._cylinder_quadric = gluNewQuadric()
            gluQuadricNormals(self._cylinder_quadric, GLU_SMOOTH)
        except Exception:
            self._sphere_quadric = None
            self._cylinder_quadric = None
    
    def resizeGL(self, width, height):
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, width / height, 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)
    
    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        # Calculate center from provider positions for stability
        center_x = center_y = center_z = 0.0
        count = 0
        try:
            pos_cache = None
            if self._provider is not None and self._template_atoms:
                # Prefer worker-provided cache during playback
                if self._positions_cache is not None and self._positions_cache_frame == self._current_frame_idx:
                    pos_cache = self._positions_cache
                else:
                    pos_cache = self._provider.get_positions(self._current_frame_idx)
                # Prefer backbone indices to reduce CPU work
                if self._backbone_indices:
                    N = len(pos_cache)
                    if self.selection_mask is None:
                        indices = [i for i in self._backbone_indices if i < N]
                    else:
                        indices = [i for i in self._backbone_indices if i < N and self.selection_mask[i]]
                else:
                    ncap = min(len(self._template_atoms), len(pos_cache))
                    if self.selection_mask is None:
                        indices = list(range(ncap))
                    else:
                        indices = [i for i in range(ncap) if self.selection_mask[i]]
                if indices:
                    arr = pos_cache[indices] if isinstance(pos_cache, np.ndarray) else np.asarray([pos_cache[i] for i in indices], dtype=np.float32)
                    sums = arr.sum(axis=0)
                    center_x = float(sums[0])
                    center_y = float(sums[1])
                    center_z = float(sums[2])
                    count = arr.shape[0]
            if count > 0:
                center_x /= count
                center_y /= count
                center_z /= count
        except Exception:
            if self.display_data:
                positions = [data['position'] for data in self.display_data]
                center_x = sum(pos[0] for pos in positions) / len(positions)
                center_y = sum(pos[1] for pos in positions) / len(positions)
                center_z = sum(pos[2] for pos in positions) / len(positions)
        
        # Set camera position
        glTranslatef(0, 0, -self.camera_distance)
        glRotatef(self.camera_rotation_x, 1, 0, 0)
        glRotatef(self.camera_rotation_y, 0, 1, 0)
        glTranslatef(-center_x, -center_y, -center_z)
        
        # Atomic modes disabled by default now; protein always as ribbon/cartoon
        rendered_any = False
        # Draw simple cartoon tube along backbone when explicitly enabled (legacy)
        if self.cartoon_enabled and self._provider and self._backbone_indices:
            try:
                pos = pos_cache if pos_cache is not None else self._provider.get_positions(self._current_frame_idx)
                backbone_points = [pos[i] for i in self._backbone_indices if i < len(pos) and (self.selection_mask is None or self.selection_mask[i])]
                if len(backbone_points) >= 3:
                    self._draw_cartoon_tube(backbone_points, max(self.cartoon_radius, 0.8), self.cartoon_color)
                    rendered_any = True
            except Exception:
                pass
        # Draw secondary-structure-aware cartoon (helix/sheet/loop)
        if self._provider and self._backbone_indices:
            try:
                pos = pos_cache if pos_cache is not None else self._provider.get_positions(self._current_frame_idx)
                N = len(pos)
                pts = [(float(pos[i][0]), float(pos[i][1]), float(pos[i][2])) for i in self._backbone_indices if i < N and (self.selection_mask is None or self.selection_mask[i])]
                if len(pts) >= 3:
                    self._render_cached_secondary_structure_cartoon(pts)
                    if getattr(self, '_cartoon_triangles', None):
                        rendered_any = True
            except Exception:
                pass

        # Draw water oxygens as small points for performance
        if self._provider and self._water_o_indices:
            try:
                self._draw_water_points(positions=pos_cache)
                if len(self._water_o_indices) > 0:
                    rendered_any = True
            except Exception:
                pass

        # Draw all non-protein, non-water residues as ball-and-stick
        if self._provider and self._ligand_groups:
            try:
                self._draw_ligands_ball_and_stick(positions=pos_cache)
                if len(self._ligand_groups) > 0:
                    rendered_any = True
            except Exception:
                pass

        # Last-resort fallback: if nothing rendered (e.g., no CA atoms found), draw atoms as points
        if not rendered_any and self.display_data:
            try:
                self._draw_atoms_points()
            except Exception:
                pass
    
    def _draw_atoms_spheres(self):
        """Atom rendering as spheres with adjustable quality"""
        sphere = self._sphere_quadric if self._sphere_quadric is not None else gluNewQuadric()
        if sphere is not self._sphere_quadric:
            try:
                gluQuadricNormals(sphere, GLU_SMOOTH)
            except Exception:
                pass
        
        for atom_data in self.display_data:
            pos = atom_data['position']
            color = atom_data['color']
            # Enlarge protein atoms
            base_radius = atom_data['radius']
            if atom_data.get('is_protein', False):
                base_radius *= self.protein_atom_scale
            radius = base_radius * self.atom_scale
            
            glPushMatrix()
            glTranslatef(pos[0], pos[1], pos[2])
            glColor3f(*color)
            
            # Use lower quality spheres for better performance
            gluSphere(sphere, radius, self.sphere_quality, self.sphere_quality)
            
            glPopMatrix()
        
        if sphere is not self._sphere_quadric:
            try:
                gluDeleteQuadric(sphere)
            except Exception:
                pass

    def _draw_atoms_points(self):
        """Very fast atom rendering using GL_POINTS"""
        glDisable(GL_LIGHTING)
        glPointSize(max(1.0, float(self.point_size)))
        if self.display_data:
            positions = np.asarray([a['position'] for a in self.display_data], dtype=np.float32)
            colors = np.asarray([a['color'] for a in self.display_data], dtype=np.float32)
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            glVertexPointerf(positions)
            glColorPointerf(colors)
            glDrawArrays(GL_POINTS, 0, positions.shape[0])
            glDisableClientState(GL_COLOR_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)
        glEnable(GL_LIGHTING)

    def _draw_water_points(self, positions=None):
        if not self._provider or not self._water_o_indices:
            return
        glDisable(GL_LIGHTING)
        glPointSize(float(self.water_point_size))
        glColor3f(*self.water_color)
        pos = positions if positions is not None else self._provider.get_positions(self._current_frame_idx)
        valid = []
        if isinstance(pos, np.ndarray):
            N = pos.shape[0]
            for idx in self._water_o_indices:
                if idx >= N:
                    continue
                if self.selection_mask is not None and (idx >= len(self.selection_mask) or not self.selection_mask[idx]):
                    continue
                valid.append((float(pos[idx][0]), float(pos[idx][1]), float(pos[idx][2])))
        else:
            sel = self.selection_mask
            max_len = len(pos)
            for idx in self._water_o_indices:
                if idx >= max_len:
                    continue
                if sel is not None and (idx >= len(sel) or not sel[idx]):
                    continue
                x, y, z = pos[idx]
                valid.append((float(x), float(y), float(z)))
        if valid:
            arr = np.asarray(valid, dtype=np.float32)
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointerf(arr)
            glDrawArrays(GL_POINTS, 0, arr.shape[0])
            glDisableClientState(GL_VERTEX_ARRAY)
        glEnable(GL_LIGHTING)

    def _draw_ligands_ball_and_stick(self, positions=None):
        if not self._provider or not self._ligand_groups:
            return
        positions = positions if positions is not None else self._provider.get_positions(self._current_frame_idx)
        # Draw bonds as cylinders first
        for key, bonds in self._ligand_bonds.items():
            chain, resid, resname = key
            is_highlight = resname.upper() in self.ligand_highlight_resnames
            bond_color = self.ligand_highlight_color if is_highlight else self.bond_color
            bond_radius = self.ligand_highlight_stick_radius if is_highlight else self.stick_radius
            for (i_idx, j_idx) in bonds:
                if i_idx >= len(positions) or j_idx >= len(positions):
                    continue
                if self.selection_mask is not None:
                    if (i_idx >= len(self.selection_mask) or j_idx >= len(self.selection_mask) or not self.selection_mask[i_idx] or not self.selection_mask[j_idx]):
                        continue
                p1 = positions[i_idx]
                p2 = positions[j_idx]
                self._draw_cylinder_between_points(p1, p2, bond_radius, bond_color, self.ligand_bond_slices)
        # Draw atoms as small spheres
        sphere = self._sphere_quadric if self._sphere_quadric is not None else gluNewQuadric()
        if sphere is not self._sphere_quadric:
            try:
                gluQuadricNormals(sphere, GLU_SMOOTH)
            except Exception:
                pass
        for key, indices in self._ligand_groups.items():
            chain, resid, resname = key
            is_highlight = resname.upper() in self.ligand_highlight_resnames
            for idx in indices:
                if idx >= len(positions):
                    continue
                if self.selection_mask is not None and (idx >= len(self.selection_mask) or not self.selection_mask[idx]):
                    continue
                atom = self._template_atoms[idx]
                x, y, z = positions[idx]
                color = self.ligand_highlight_color if is_highlight else ATOMIC_COLORS.get(atom.element.upper(), (0.8, 0.8, 0.8))
                glPushMatrix()
                glTranslatef(float(x), float(y), float(z))
                glColor3f(*color)
                base_scale = self.ligand_highlight_atom_scale if is_highlight else self.ligand_atom_scale
                radius = atom.radius * base_scale
                gluSphere(sphere, radius, max(8, self.sphere_quality // 2), max(8, self.sphere_quality // 2))
                glPopMatrix()
        if sphere is not self._sphere_quadric:
            try:
                gluDeleteQuadric(sphere)
            except Exception:
                pass

    def _draw_cylinder_between_points(self, p1, p2, radius, color, slices):
        # Build cylinder aligned with vector p2 - p1
        x1, y1, z1 = map(float, p1)
        x2, y2, z2 = map(float, p2)
        vx, vy, vz = x2 - x1, y2 - y1, z2 - z1
        length = math.sqrt(vx*vx + vy*vy + vz*vz)
        if length < 1e-5:
            return
        # Normalize direction
        dx, dy, dz = vx/length, vy/length, vz/length
        # Find rotation axis from cylinder's default (0,0,1) to (dx,dy,dz)
        ax, ay, az = -dy, dx, 0.0
        angle_rad = math.acos(max(-1.0, min(1.0, dz)))
        angle_deg = angle_rad * 180.0 / math.pi
        glPushMatrix()
        glTranslatef(x1, y1, z1)
        glColor3f(*color)
        # Handle degenerate axis when vector is near Z axis
        if abs(angle_deg) > 1e-3:
            glRotatef(angle_deg, float(ax), float(ay), float(az))
        quad = self._cylinder_quadric if self._cylinder_quadric is not None else gluNewQuadric()
        if quad is not self._cylinder_quadric:
            try:
                gluQuadricNormals(quad, GLU_SMOOTH)
            except Exception:
                pass
        gluCylinder(quad, radius, radius, length, max(6, slices), 1)
        # Cap ends with disks
        gluDisk(quad, 0.0, radius, max(6, slices), 1)
        glTranslatef(0.0, 0.0, length)
        gluDisk(quad, 0.0, radius, max(6, slices), 1)
        if quad is not self._cylinder_quadric:
            try:
                gluDeleteQuadric(quad)
            except Exception:
                pass
        glPopMatrix()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.last_mouse_pos = event.position()
    
    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.last_mouse_pos:
            dx = event.position().x() - self.last_mouse_pos.x()
            dy = event.position().y() - self.last_mouse_pos.y()
            
            self.camera_rotation_y += dx * 0.5
            self.camera_rotation_x += dy * 0.5
            
            self.update()
            self.last_mouse_pos = event.position()
    
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.camera_distance *= 1.0 - delta / 1000.0
        self.camera_distance = max(5.0, min(200.0, self.camera_distance))
        self.update()
    
    def shutdown(self):
        try:
            self.render_worker.requestInterruption()
            self.render_worker.quit()
            self.render_worker.wait(2000)
        except Exception:
            pass

    def _draw_cartoon(self, points: List[Tuple[float, float, float]], radius: float, color: Tuple[float, float, float]):
        # Deprecated by _draw_cartoon_tube
        if len(points) < 2:
            return
        self._draw_cartoon_tube(points, radius, color)

    def _draw_cartoon_tube(self, points: List[Tuple[float, float, float]], radius: float, color: Tuple[float, float, float]):
        if len(points) < 3:
            return
        # Smooth backbone with Catmull-Rom spline
        smooth_pts = self._smooth_polyline(points, max(4, self.ribbon_smooth_segments))
        if len(smooth_pts) < 3:
            return
        ring_slices = max(8, self.tube_segments)
        glColor3f(*color)
        # Build tubes by drawing triangle strips between consecutive rings
        prev_ring = None
        prev_normal = None
        up_ref = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        step = max(1, self.tube_step)
        for i in range(1, len(smooth_pts)-1, step):
            p_prev = np.array(smooth_pts[i - 1], dtype=np.float32)
            p_curr = np.array(smooth_pts[i], dtype=np.float32)
            p_next = np.array(smooth_pts[i + 1], dtype=np.float32)
            T = p_next - p_prev
            norm = np.linalg.norm(T)
            if norm < 1e-6:
                if prev_ring is None:
                    continue
                T = prev_normal if prev_normal is not None else np.array([1.0, 0.0, 0.0], dtype=np.float32)
            else:
                T = T / norm
            # Initialize normal not parallel to T
            if prev_normal is None:
                n0 = up_ref
                if abs(np.dot(T, n0)) > 0.9:
                    n0 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                N = n0 - np.dot(n0, T) * T
                nlen = np.linalg.norm(N)
                N = N / (nlen if nlen > 1e-6 else 1.0)
            else:
                N = prev_normal - np.dot(prev_normal, T) * T
                nlen = np.linalg.norm(N)
                if nlen < 1e-6:
                    N = up_ref - np.dot(up_ref, T) * T
                    nlen = np.linalg.norm(N)
                N = N / (nlen if nlen > 1e-6 else 1.0)
            B = np.cross(T, N)
            blen = np.linalg.norm(B)
            if blen > 1e-6:
                B = B / blen
            # Build ring vertices
            ring = []
            for k in range(ring_slices):
                theta = (2.0 * math.pi * k) / ring_slices
                offset = math.cos(theta) * N * radius + math.sin(theta) * B * radius
                v = p_curr + offset
                ring.append(v)
            if prev_ring is not None:
                glBegin(GL_TRIANGLE_STRIP)
                for k in range(ring_slices + 1):
                    k0 = k % ring_slices
                    v_prev = prev_ring[k0]
                    v_curr = ring[k0]
                    # Approximate normal as offset direction for current ring
                    off_dir = v_curr - p_curr
                    nlen2 = np.linalg.norm(off_dir)
                    nrm = off_dir / (nlen2 if nlen2 > 1e-6 else 1.0)
                    glNormal3f(float(nrm[0]), float(nrm[1]), float(nrm[2]))
                    glVertex3f(float(v_prev[0]), float(v_prev[1]), float(v_prev[2]))
                    glVertex3f(float(v_curr[0]), float(v_curr[1]), float(v_curr[2]))
                glEnd()
            prev_ring = ring
            prev_normal = N

    def _draw_ribbon(self, points: List[Tuple[float, float, float]], width: float, twist_deg: float, smooth_segments: int):
        # Deprecated by _draw_secondary_structure_cartoon
        if len(points) < 3:
            return
        self._draw_secondary_structure_cartoon(points)

    def _draw_secondary_structure_cartoon(self, points: List[Tuple[float, float, float]]):
        if len(points) < 3:
            return
        # Smooth backbone moderately
        pts = self._smooth_polyline(points, max(4, self.ribbon_smooth_segments))
        n = len(pts)
        if n < 3:
            return
        # Resample secondary structure labels to smoothed points length
        ss = getattr(self, '_ss_assignments', None)
        if not ss:
            ss = ['C'] * n
        else:
            if len(ss) != n:
                scaled = []
                for i in range(n):
                    j = int(i * (len(ss) - 1) / max(1, n - 1))
                    scaled.append(ss[min(j, len(ss)-1)])
                ss = scaled

        # Compute smooth frames (T, N, B) for each interior point
        up_ref = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        T_list: List[np.ndarray] = [None] * n  # type: ignore
        N_list: List[np.ndarray] = [None] * n  # type: ignore
        B_list: List[np.ndarray] = [None] * n  # type: ignore
        prev_T = None
        prev_N = None
        for i in range(1, n - 1):
            p_prev = np.array(pts[i - 1], dtype=np.float32)
            p_curr = np.array(pts[i], dtype=np.float32)
            p_next = np.array(pts[i + 1], dtype=np.float32)
            T = p_next - p_prev
            norm = np.linalg.norm(T)
            if norm < 1e-6:
                T = prev_T if prev_T is not None else np.array([1.0, 0.0, 0.0], dtype=np.float32)
            else:
                T = T / norm
            if prev_N is None:
                base = up_ref
                if abs(np.dot(T, base)) > 0.9:
                    base = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                N = base - np.dot(base, T) * T
                nlen = np.linalg.norm(N)
                N = N / (nlen if nlen > 1e-6 else 1.0)
            else:
                N = prev_N - np.dot(prev_N, T) * T
                nlen = np.linalg.norm(N)
                if nlen < 1e-6:
                    N = up_ref - np.dot(up_ref, T) * T
                    nlen = np.linalg.norm(N)
                N = N / (nlen if nlen > 1e-6 else 1.0)
            B = np.cross(T, N)
            blen = np.linalg.norm(B)
            if blen > 1e-6:
                B = B / blen
            T_list[i] = T
            N_list[i] = N
            B_list[i] = B
            prev_T = T
            prev_N = N

        # Helper to collect contiguous runs of the same SS mode
        def contiguous_runs(labels: List[str]) -> List[Tuple[str, int, int]]:
            runs = []
            if len(labels) < 2:
                return runs
            cur = labels[1]
            start = 1
            for i in range(2, len(labels) - 1):
                if labels[i] != cur:
                    runs.append((cur, start, i))  # [start, i)
                    cur = labels[i]
                    start = i
            runs.append((cur, start, len(labels) - 1))
            return runs

        runs = contiguous_runs(ss)
        if not runs:
            return

        # Sweep geometry per run
        for mode, s, e in runs:
            centers = [np.array(pts[k], dtype=np.float32) for k in range(s, e)]
            Ts = [T_list[k] for k in range(s, e)]
            Ns = [N_list[k] for k in range(s, e)]
            Bs = [B_list[k] for k in range(s, e)]
            # Sanity filter
            valid = [i for i in range(len(centers)) if Ts[i] is not None and Ns[i] is not None and Bs[i] is not None]
            if len(valid) < 2:
                continue
            centers = [centers[i] for i in valid]
            Ts = [Ts[i] for i in valid]
            Ns = [Ns[i] for i in valid]
            Bs = [Bs[i] for i in valid]
            base_idx = s
            if mode == 'H':
                color = self.ss_colors['H']
                # Estimate per-step twist scaled by local step length to keep helix uniform
                # average step length in this run
                step_lengths = []
                for i2 in range(1, len(centers)):
                    step_lengths.append(float(np.linalg.norm(centers[i2] - centers[i2 - 1])))
                avg_step = max(1e-3, (sum(step_lengths) / len(step_lengths)) if step_lengths else self.helix_ref_step_len)
                twist_per_step = self.helix_twist_deg * (avg_step / self.helix_ref_step_len)
                self._sweep_helix_ribbon(centers, Ts, Ns, Bs, self.helix_width, self.helix_thickness, twist_per_step, color, base_idx)
            elif mode == 'E':
                color = self.ss_colors['E']
                sheet_thickness = max(0.5, self.sheet_width * 0.28)
                add_arrow = True
                self._sweep_sheet(centers, Ts, Ns, Bs, self.sheet_width, sheet_thickness, color, add_arrow, base_idx)
            else:
                # Tube only for straight, non-arrow leftovers; otherwise prefer arrow for mild bends
                # Decide per-run if should be rendered as arrow instead of tube
                avg_turn = 0.0
                if len(centers) > 2:
                    acc = 0.0
                    cnt = 0
                    for ii in range(1, len(centers) - 1):
                        v1 = centers[ii] - centers[ii - 1]
                        v2 = centers[ii + 1] - centers[ii]
                        a1 = float(np.linalg.norm(v1))
                        a2 = float(np.linalg.norm(v2))
                        if a1 > 1e-6 and a2 > 1e-6:
                            ca = float(np.dot(v1, v2) / (a1 * a2))
                            ca = max(-1.0, min(1.0, ca))
                            acc += math.acos(ca)
                            cnt += 1
                    avg_turn = (acc / cnt) if cnt > 0 else 3.14
                if avg_turn <= 0.9:  # prefer arrow for only mildly bent coils
                    color = self.ss_colors['E']
                    sheet_thickness = max(0.5, self.sheet_width * 0.28)
                    self._sweep_sheet(centers, Ts, Ns, Bs, self.sheet_width, sheet_thickness, color, add_arrow=True, base_idx=base_idx)
                else:
                    color = self.ss_colors['C']
                    loop_radius = max(0.8, self.loop_width * 0.6)
                    self._sweep_tube(centers, Ts, Ns, Bs, loop_radius, color, base_idx)

    def _sweep_tube(self, centers, Ts, Ns, Bs, radius, color, base_idx):
        ring_slices = max(12, self.tube_segments)
        prev_ring = None
        for i in range(len(centers)):
            c = centers[i]
            N = Ns[i]
            B = Bs[i]
            ring = []
            for k in range(ring_slices):
                theta = (2.0 * math.pi * k) / ring_slices
                off = math.cos(theta) * N * radius + math.sin(theta) * B * radius
                ring.append(c + off)
            if prev_ring is not None:
                for k in range(ring_slices):
                    k0 = k
                    k1 = (k + 1) % ring_slices
                    v00 = prev_ring[k0]
                    v01 = prev_ring[k1]
                    v10 = ring[k0]
                    v11 = ring[k1]
                    # Normals are radial from current center for smoother shading
                    n10 = (v10 - c)
                    n10 = n10 / (np.linalg.norm(n10) if np.linalg.norm(n10) > 1e-6 else 1.0)
                    n11 = (v11 - c)
                    n11 = n11 / (np.linalg.norm(n11) if np.linalg.norm(n11) > 1e-6 else 1.0)
                    n00 = n10
                    n01 = n11
                    # Two triangles per quad
                    self._append_tri(v00, n00, v10, n10, v11, n11, color, base_idx + i)
                    self._append_tri(v00, n00, v11, n11, v01, n01, color, base_idx + i)
            prev_ring = ring

    def _sweep_sheet(self, centers, Ts, Ns, Bs, width, thickness, color, add_arrow, base_idx):
        # Build a rectangular ribbon with finite thickness (a thin prism) and optional arrow tip at the end
        half = width * 0.5
        prev = None
        for i in range(len(centers)):
            c = centers[i]
            T = Ts[i]
            N = Ns[i]
            B = Bs[i]
            # Gentle twist alignment towards B to prevent flipping in sharp turns
            if i > 0 and prev is not None:
                _, _, _, _, pN, pB, pT, _ = prev
                # Keep N continuous by flipping if needed
                if np.dot(N, pN) < 0:
                    N = -N
                    B = -B
            left = c - N * half
            right = c + N * half
            top_left = left + B * (thickness * 0.5)
            top_right = right + B * (thickness * 0.5)
            bot_left = left - B * (thickness * 0.5)
            bot_right = right - B * (thickness * 0.5)
            frame = (top_left, top_right, bot_left, bot_right, N, B, T, c)
            if prev is not None:
                p_tl, p_tr, p_bl, p_br, pN, pB, pT, pc = prev
                # Top face (two triangles)
                self._append_tri(p_tl, pN, top_left, N, top_right, N, color, base_idx + i)
                self._append_tri(p_tl, pN, top_right, N, p_tr, pN, color, base_idx + i)
                # Bottom face
                self._append_tri(p_bl, -pN, bot_right, -N, bot_left, -N, color, base_idx + i)
                self._append_tri(p_bl, -pN, p_br, -pN, bot_right, -N, color, base_idx + i)
                # Left side
                self._append_tri(p_bl, -pB, bot_left, -B, top_left, B, color, base_idx + i)
                self._append_tri(p_bl, -pB, top_left, B, p_tl, pB, color, base_idx + i)
                # Right side
                self._append_tri(p_tr, pB, top_right, B, bot_right, -B, color, base_idx + i)
                self._append_tri(p_tr, pB, bot_right, -B, p_br, -pB, color, base_idx + i)
            prev = frame

        # Arrow tip at the end of the sheet run (restore arrow reliably)
        if add_arrow and prev is not None and len(centers) >= 2:
            p_tl, p_tr, p_bl, p_br, pN, pB, pT, pc = prev
            if np.linalg.norm(pT) < 1e-6:
                return
            tip_center = pc + pT * self.arrow_length
            tip_top = tip_center + pB * (thickness * 0.5)
            tip_bot = tip_center - pB * (thickness * 0.5)
            # Widen arrow mouth slightly vs body
            widen = 1.15
            tl = p_tl + (p_tl - pc) * (widen - 1.0)
            tr = p_tr + (p_tr - pc) * (widen - 1.0)
            bl = p_bl + (p_bl - pc) * (widen - 1.0)
            br = p_br + (p_br - pc) * (widen - 1.0)
            # Top arrow (triangle)
            self._append_tri(tl, pN, tr, pN, tip_top, pN, color, base_idx + len(centers))
            # Bottom arrow
            self._append_tri(bl, -pN, tip_bot, -pN, br, -pN, color, base_idx + len(centers))
            # Connect sides to tip (left)
            self._append_tri(bl, -pB, tip_bot, -pB, tip_top, pB, color, base_idx + len(centers))
            self._append_tri(bl, -pB, tip_top, pB, tl, pB, color, base_idx + len(centers))
            # Connect sides to tip (right)
            self._append_tri(tr, pB, tip_top, pB, tip_bot, -pB, color, base_idx + len(centers))
            self._append_tri(tr, pB, tip_bot, -pB, br, -pB, color, base_idx + len(centers))

    def _sweep_helix_ribbon(self, centers, Ts, Ns, Bs, width, thickness, twist_deg_per_step, color, base_idx):
        # Sweep a twisted ribbon (finite thickness) along the helix segment
        # Use parallel transport to minimize frame twisting artifacts (closer to NGL/Chimera look)
        half = width * 0.5
        prev = None
        current_rot_deg = 0.0
        prevN = None
        for i in range(len(centers)):
            c = centers[i]
            T = Ts[i]
            N = Ns[i]
            B = Bs[i]
            # Parallel transport correction: keep N direction consistent
            if prevN is not None and np.dot(N, prevN) < 0:
                N = -N
                B = -B
            prevN = N
            # Rotate the ribbon frame around the tangent T
            angle = math.radians(current_rot_deg)
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            N_rot = N * cos_a + B * sin_a
            B_rot = -N * sin_a + B * cos_a
            # Build top/bottom faces with thickness and current twist angle
            left = c - N_rot * half
            right = c + N_rot * half
            top_left = left + B_rot * (thickness * 0.5)
            top_right = right + B_rot * (thickness * 0.5)
            bot_left = left - B_rot * (thickness * 0.5)
            bot_right = right - B_rot * (thickness * 0.5)
            frame = (top_left, top_right, bot_left, bot_right, N_rot, B_rot, T, c)
            if prev is not None:
                p_tl, p_tr, p_bl, p_br, pN, pB, pT, pc = prev
                # Top face (two triangles)
                self._append_tri(p_tl, pN, top_left, N_rot, top_right, N_rot, color, base_idx + i)
                self._append_tri(p_tl, pN, top_right, N_rot, p_tr, pN, color, base_idx + i)
                # Bottom face
                self._append_tri(p_bl, -pN, bot_right, -N_rot, bot_left, -N_rot, color, base_idx + i)
                self._append_tri(p_bl, -pN, p_br, -pN, bot_right, -N_rot, color, base_idx + i)
                # Left side
                self._append_tri(p_bl, -pB, bot_left, -B_rot, top_left, B_rot, color, base_idx + i)
                self._append_tri(p_bl, -pB, top_left, B_rot, p_tl, pB, color, base_idx + i)
                # Right side
                self._append_tri(p_tr, pB, top_right, B_rot, bot_right, -B_rot, color, base_idx + i)
                self._append_tri(p_tr, pB, bot_right, -B_rot, p_br, -pB, color, base_idx + i)
            prev = frame
            current_rot_deg += twist_deg_per_step

    def _render_cached_secondary_structure_cartoon(self, points: List[Tuple[float, float, float]]):
        # If disk precompute for this frame exists and no selection mask (full protein), load directly
        if self._precompute_dir and (self.selection_mask is None):
            store = PrecomputedCartoonStore(self._precompute_dir)
            data = store.read_frame(self._current_frame_idx)
            if data is not None:
                v, n, c = data
                self._cartoon_vertices = v
                self._cartoon_normals = n
                self._cartoon_colors = c
                self._cartoon_arrays_version += 1
                self._cartoon_arrays_built_for_version = self._cartoon_arrays_version
                # Fast path render
                glEnableClientState(GL_VERTEX_ARRAY)
                glEnableClientState(GL_NORMAL_ARRAY)
                glEnableClientState(GL_COLOR_ARRAY)
                glVertexPointerf(v)
                glNormalPointerf(n)
                glColorPointerf(c)
                glDrawArrays(GL_TRIANGLES, 0, v.shape[0])
                glDisableClientState(GL_COLOR_ARRAY)
                glDisableClientState(GL_NORMAL_ARRAY)
                glDisableClientState(GL_VERTEX_ARRAY)
                return
        # Rebuild cache only if inputs changed: frame index or selection set length/hash
        sel_key = None
        if self.selection_mask is not None:
            # compact selection key using small hash
            true_count = sum(1 for x in self.selection_mask if x)
            sel_key = (len(self.selection_mask), true_count)
        if (not self._cartoon_cache_valid or
            self._cartoon_cached_frame_idx != self._current_frame_idx or
            self._cartoon_cached_sel_key != sel_key):
            self._cartoon_triangles = []
            self._draw_secondary_structure_cartoon(points)
            self._cartoon_cache_valid = True
            self._cartoon_cached_frame_idx = self._current_frame_idx
            self._cartoon_cached_sel_key = sel_key
            # mark client arrays dirty
            self._cartoon_arrays_version += 1
        # Build client arrays on demand for the current version
        if self._cartoon_arrays_built_for_version != self._cartoon_arrays_version and self._cartoon_triangles:
            tris = self._cartoon_triangles
            num = len(tris)
            v = np.empty((num * 3, 3), dtype=np.float32)
            n = np.empty((num * 3, 3), dtype=np.float32)
            c = np.empty((num * 3, 3), dtype=np.float32)
            idx = 0
            for (v1, n1, v2, n2, v3, n3, col, _) in tris:
                v[idx] = v1; n[idx] = n1; c[idx] = col; idx += 1
                v[idx] = v2; n[idx] = n2; c[idx] = col; idx += 1
                v[idx] = v3; n[idx] = n3; c[idx] = col; idx += 1
            self._cartoon_vertices = v
            self._cartoon_normals = n
            self._cartoon_colors = c
            self._cartoon_arrays_built_for_version = self._cartoon_arrays_version
        # Render using client-side arrays if available
        if self._cartoon_vertices is not None and self._cartoon_normals is not None and self._cartoon_colors is not None:
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            glVertexPointerf(self._cartoon_vertices)
            glNormalPointerf(self._cartoon_normals)
            glColorPointerf(self._cartoon_colors)
            glDrawArrays(GL_TRIANGLES, 0, self._cartoon_vertices.shape[0])
            glDisableClientState(GL_COLOR_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)

    def _append_tri(self, v1, n1, v2, n2, v3, n3, color, idx):
        self._cartoon_triangles.append((
            (float(v1[0]), float(v1[1]), float(v1[2])),
            (float(n1[0]), float(n1[1]), float(n1[2])),
            (float(v2[0]), float(v2[1]), float(v2[2])),
            (float(n2[0]), float(n2[1]), float(n2[2])),
            (float(v3[0]), float(v3[1]), float(v3[2])),
            (float(n3[0]), float(n3[1]), float(n3[2])),
            (float(color[0]), float(color[1]), float(color[2])),
            int(idx)
        ))

    def _append_tube_section_triangles(self, center, T, N, B, radius, color, idx):
        ring_slices = max(8, self.tube_segments)
        # Build small disk fan facing along normal N; approximate tube by overlapping fans (medium performance)
        c = np.array(center, dtype=np.float32)
        for k in range(ring_slices):
            theta0 = (2.0 * math.pi * k) / ring_slices
            theta1 = (2.0 * math.pi * (k + 1)) / ring_slices
            off0 = math.cos(theta0) * N * radius + math.sin(theta0) * B * radius
            off1 = math.cos(theta1) * N * radius + math.sin(theta1) * B * radius
            v0 = c
            v1 = c + off0
            v2 = c + off1
            n0 = N
            n1 = off0 / (np.linalg.norm(off0) if np.linalg.norm(off0) > 1e-6 else 1.0)
            n2 = off1 / (np.linalg.norm(off1) if np.linalg.norm(off1) > 1e-6 else 1.0)
            self._append_tri(v0, n0, v1, n1, v2, n2, color, idx)

    def _append_sheet_section_triangles(self, center, T, N, B, width, color, draw_arrow, idx):
        half = width * 0.5
        c = np.array(center, dtype=np.float32)
        left = c - N * half
        right = c + N * half
        advance = T * 0.8
        left2 = left + advance
        right2 = right + advance
        # Two triangles for the quad
        self._append_tri(left, N, right, N, right2, N, color, idx)
        self._append_tri(left, N, right2, N, left2, N, color, idx)
        if draw_arrow:
            tip = c + T * self.arrow_length
            self._append_tri(left, N, right, N, tip, N, color, idx)

    def _draw_tube_section(self, center, T, N, B, radius, color):
        glColor3f(*color)
        ring_slices = max(8, self.tube_segments)
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(float(N[0]), float(N[1]), float(N[2]))
        glVertex3f(float(center[0]), float(center[1]), float(center[2]))
        for k in range(ring_slices + 1):
            theta = (2.0 * math.pi * k) / ring_slices
            offset = math.cos(theta) * N * radius + math.sin(theta) * B * radius
            v = center + offset
            glNormal3f(float(offset[0]), float(offset[1]), float(offset[2]))
            glVertex3f(float(v[0]), float(v[1]), float(v[2]))
        glEnd()

    def _draw_sheet_section(self, center, T, N, B, width, color, draw_arrow=False):
        glColor3f(*color)
        half = width * 0.5
        left = center - N * half
        right = center + N * half
        glBegin(GL_QUADS)
        glNormal3f(float(N[0]), float(N[1]), float(N[2]))
        glVertex3f(float(left[0]), float(left[1]), float(left[2]))
        glVertex3f(float(right[0]), float(right[1]), float(right[2]))
        # advance a little along T to give strip body
        advance = T * 0.8
        left2 = left + advance
        right2 = right + advance
        glVertex3f(float(right2[0]), float(right2[1]), float(right2[2]))
        glVertex3f(float(left2[0]), float(left2[1]), float(left2[2]))
        glEnd()
        if draw_arrow:
            # draw a small triangular arrow tip
            tip = center + T * self.arrow_length
            v1 = center - N * half
            v2 = center + N * half
            glBegin(GL_TRIANGLES)
            glNormal3f(float(N[0]), float(N[1]), float(N[2]))
            glVertex3f(float(v1[0]), float(v1[1]), float(v1[2]))
            glVertex3f(float(v2[0]), float(v2[1]), float(v2[2]))
            glVertex3f(float(tip[0]), float(tip[1]), float(tip[2]))
            glEnd()

    def _smooth_polyline(self, points: List[Tuple[float, float, float]], segments: int) -> List[Tuple[float, float, float]]:
        if segments <= 1 or len(points) < 4:
            return [tuple(map(float, p)) for p in points]
        pts = [np.array(p, dtype=np.float32) for p in points]
        out: List[Tuple[float, float, float]] = []
        for i in range(len(pts) - 3):
            p0, p1, p2, p3 = pts[i], pts[i+1], pts[i+2], pts[i+3]
            for j in range(segments):
                t = j / float(segments)
                t2 = t * t
                t3 = t2 * t
                # Catmull-Rom spline (centripetal variant can be added later)
                a = -0.5*t3 + t2 - 0.5*t
                b = 1.5*t3 - 2.5*t2 + 1.0
                c = -1.5*t3 + 2.0*t2 + 0.5*t
                d = 0.5*t3 - 0.5*t2
                pt = a*p0 + b*p1 + c*p2 + d*p3
                out.append((float(pt[0]), float(pt[1]), float(pt[2])))
        out.append(tuple(map(float, pts[-2])))
        out.append(tuple(map(float, pts[-1])))
        return out

class TrajectoryLoader(QThread):
    progress_updated = Signal(int)
    frame_loaded = Signal(int)
    finished_loading = Signal(list)
    status_message = Signal(str)
    
    def __init__(self, gro_file: Optional[str] = None, xtc_file: Optional[str] = None):
        super().__init__()
        self.gro_file = gro_file
        self.xtc_file = xtc_file
        self._gro_topology_path = gro_file
    
    def run(self):
        try:
            self.status_message.emit("Loading GRO file...")
            self.progress_updated.emit(10)
            
            # Load GRO file
            if not self.gro_file:
                raise ValueError("GRO topology path is required to load trajectory")
            gro_frame = GromacsReader.read_gro_file(self.gro_file)
            frames = [gro_frame]
            
            self.progress_updated.emit(20)
            
            # Load XTC trajectory if provided
            if self.xtc_file:
                self.status_message.emit("Reading XTC trajectory...")
                
                def frame_progress(frame_count):
                    progress = 20 + int((frame_count / 100) * 70)  # 20-90%
                    self.progress_updated.emit(min(progress, 90))
                    self.frame_loaded.emit(frame_count)
                
                # We do not pre-load all frames into RAM. Build a streaming provider instead.
                provider = None
                try:
                    import MDAnalysis  # noqa: F401
                    provider = MDAnalysisProvider(self._gro_topology_path, self.xtc_file)
                    total = provider.get_num_frames()
                    # Emit some progress ticks without storing frames
                    for i in range(min(5, total)):
                        _ = provider.get_positions(i)
                        frame_progress(i + 1)
                    self.status_message.emit(f"Trajectory ready (streaming): {total} frames")
                    # Kick off precomputation of cartoon geometry across frames
                    try:
                        def _pc_progress(done, tot):
                            # Map 90-99% to precompute progress
                            pct = 90 + int(9 * (done / max(1, tot)))
                            self.progress_updated.emit(min(99, pct))
                        precompute_cartoon_geometry(provider, gro_frame.atoms, self._gro_topology_path, self.xtc_file, _pc_progress)
                        self.status_message.emit("Precompute finished")
                    except Exception as _e:
                        # Non-fatal
                        self.status_message.emit(f"Precompute skipped: {_e}")
                except Exception as e:
                    # Fallback: minimal reader but restrict preloading for memory safety
                    self.status_message.emit(f"MDAnalysis unavailable or failed ({e}); using fallback reader with capped preload")
                    xtc_frames = GromacsReader.read_xtc_file(
                        self.xtc_file, gro_frame, frame_progress, self._gro_topology_path)
                    # Keep only first and last few frames to save memory
                    keep_head = xtc_frames[:2]
                    keep_tail = xtc_frames[-2:] if len(xtc_frames) > 4 else []
                    frames = [gro_frame] + keep_head + keep_tail
                    self.finished_loading.emit(frames)
                    return
                
                # Attach provider info to the loader instance for the UI to pick up
                self.provider = provider
                self.frames_streaming = True
            else:
                self.provider = None
                self.frames_streaming = False
            
            self.progress_updated.emit(100)
            if getattr(self, 'frames_streaming', False):
                self.status_message.emit("GRO loaded, trajectory streaming ready")
            else:
                self.status_message.emit(f"Loaded {len(frames)} frames")
            self.finished_loading.emit(frames)
            
        except Exception as e:
            self.status_message.emit(f"Error loading trajectory: {e}")
            self.finished_loading.emit([])

class _PreloadedProvider(BaseTrajectoryProvider):
    def __init__(self, frames: List[Frame]):
        self._frames = frames
    def get_num_frames(self) -> int:
        return len(self._frames)
    def get_positions(self, frame_index: int):
        frame = self._frames[min(frame_index, len(self._frames) - 1)]
        return [(a.x, a.y, a.z) for a in frame.atoms]
    def get_time(self, frame_index: int) -> float:
        frame = self._frames[min(frame_index, len(self._frames) - 1)]
        return float(frame.time)
    def get_box(self, frame_index: int):
        frame = self._frames[min(frame_index, len(self._frames) - 1)]
        return frame.box

    def keyPressEvent(self, event):
        pass
