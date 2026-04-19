"""
Resource Builder Utility
Use this script to manually rebuild resource files.

Usage:
    python build_resources.py          # Build resources
    python build_resources.py --force  # Force rebuild even if up-to-date
    python build_resources.py --info   # Show resource status
"""

import sys
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description="VERA Resource Builder")
    parser.add_argument("--force", action="store_true", 
                       help="Force rebuild even if resources are up-to-date")
    parser.add_argument("--info", action="store_true", 
                       help="Show resource status information")
    parser.add_argument("--clean", action="store_true", 
                       help="Clean resource files and rebuild")
    
    args = parser.parse_args()
    
    try:
        from backend.resource_manager import get_resource_manager
        
        manager = get_resource_manager()
        
        if args.info:
            print("=== VERA Resource Status ===")
            print(f"Project root: {manager.project_root}")
            print(f"Theme folder: {manager.theme_dir} ({'exists' if manager.theme_dir.exists() else 'missing'})")
            print(f"Web folder: {manager.web_dir} ({'exists' if manager.web_dir.exists() else 'missing'})")
            print(f"Assets folder: {manager.assets_dir} ({'exists' if manager.assets_dir.exists() else 'missing'})")
            print()
            print(f"QRC file: {manager.qrc_file} ({'exists' if manager.qrc_file.exists() else 'missing'})")
            print(f"Python resource: {manager.py_resource_file} ({'exists' if manager.py_resource_file.exists() else 'missing'})")
            print(f"Manifest: {manager.manifest_file} ({'exists' if manager.manifest_file.exists() else 'missing'})")
            print()
            print(f"Using compiled resources: {manager.is_using_resources()}")
            
            # Show resource contents if available
            if manager.manifest_file.exists():
                manifest = manager._load_manifest()
                if manifest:
                    print(f"Resource manifest: {manifest.total_count} files")
                    print(f"Created: {manifest.created_at}")
                    
                    # Show file breakdown by type
                    file_types = {}
                    for file_path in manifest.files:
                        ext = Path(file_path).suffix.lower()
                        file_types[ext] = file_types.get(ext, 0) + 1
                    
                    print("File types:")
                    for ext, count in sorted(file_types.items()):
                        print(f"  {ext or '(no extension)'}: {count}")
            
            return
        
        if args.clean:
            print("Cleaning resource files...")
            for file_path in [manager.qrc_file, manager.py_resource_file, manager.manifest_file]:
                if file_path.exists():
                    file_path.unlink()
                    print(f"Removed: {file_path}")
        
        if args.force or args.clean:
            print("Force rebuilding resources...")
            success = manager.force_rebuild()
        else:
            print("Checking and building resources...")
            success = manager.ensure_resources()
        
        if success:
            print("✅ Resource build successful!")
            
            # Show summary
            if manager.manifest_file.exists():
                manifest = manager._load_manifest()
                if manifest:
                    print(f"Built resource with {manifest.total_count} files")
            else:
                print("No manifest created (no files found?)")
        else:
            print("❌ Resource build failed!")
            sys.exit(1)
            
    except ImportError as e:
        print(f"❌ Failed to import resource manager: {e}")
        print("Make sure you're running this from the project root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Resource build error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
