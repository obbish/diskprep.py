import os
import sys
import subprocess
import signal
import shutil

class TempFileManager:
    def __init__(self):
        self.temp_files = []

    def add_temp_file(self, filename):
        self.temp_files.append(filename)
        if not os.path.isfile(filename):
            open(filename, 'w').close()

    def remove_temp_files(self):
        for temp_file in self.temp_files:
            if os.path.isfile(temp_file):
                os.remove(temp_file)
        self.temp_files.clear()

temp_file_manager = TempFileManager()

def cleanup(signum, frame):
    temp_file_manager.remove_temp_files()
    print("\nProcess interrupted. Exiting.")
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)

def clear_terminal():
    clear_command = 'cls' if os.name == 'nt' else 'clear'
    try:
        if shutil.which(clear_command):
            subprocess.run(clear_command, check=True)
        else:
            print("\n" * shutil.get_terminal_size().lines)
    except Exception as e:
        print(f"Could not clear terminal: {e}")
        print("\n" * 10)

def execute_command(command):
    """Run the dd command, display real-time output on a single line, and handle 'disk full' message."""
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Process output in real-time from stderr (where dd sends progress)
        for line in process.stderr:
            if "No space left on device" in line:
                print("\nDisk full; moving to the next pass.")
                process.terminate()
                break
            print(f"\r{line.strip()}", end='', flush=True)

        process.wait()  # Ensure the process completes fully
        print()  # New line after completion
    except subprocess.CalledProcessError as e:
        print(f"Unexpected error: {e}")
        raise

def stream_source(pass_type, device, block_size, count=None):
    command = ["dd", "if=/dev/urandom" if pass_type == "random" else "if=/dev/zero", 
               f"of={device}", f"bs={block_size}", "status=progress"]
    if count:
        command.append(f"count={count}")
    return command

def path_source(pass_type, device, block_size, count=None, content=None):
    """Build command list for file-based data sources like ones, string, and file."""
    temp_file = None
    
    if pass_type == "ones":
        temp_file = "ones_source.tmp"
        if not os.path.isfile(temp_file):
            with open(temp_file, "wb") as f:
                f.write(b"\xFF" * (1024 * 1024 * 256))  # 256MB of 0xFF bytes
        temp_file_manager.add_temp_file(temp_file)
    
    elif pass_type == "string":
        temp_file = "string_source.tmp"
        if not os.path.isfile(temp_file):
            with open(temp_file, "wb") as f:
                # Repeat the string to fill a 256MB file without modifying it
                chunk = content.encode()
                for _ in range(256 * 1024 * 1024 // len(chunk)):
                    f.write(chunk)
        temp_file_manager.add_temp_file(temp_file)
    
    elif pass_type == "file":
        temp_file = content
        if not os.path.isfile(temp_file):
            print(f"Error: File not found at {temp_file}. Skipping this pass.")
            return None

    # Construct the command to use the temp file with dd
    if count:
        command = ["dd", f"if={temp_file}", f"of={device}", f"bs={block_size}", f"count={count}", "status=progress"]
    else:
        command = ["dd", f"if={temp_file}", f"of={device}", f"bs={block_size}", "status=progress"]
    
    return command

def perform_pass(pass_info, device):
    pass_type = pass_info["type"]
    block_size = pass_info["block_size"]
    count = pass_info.get("count")
    content = pass_info.get("content")

    if pass_type in ["random", "zeros"]:
        command = stream_source(pass_type, device, block_size, count)
        execute_command(command)
    else:
        command = path_source(pass_type, device, block_size, count, content)
        if command:
            execute_command(command)

def configure_passes(device):
    passes = []
    clear_terminal()
    print(f"Create your custom pass schema for drive: {device}\n")
    
    while True:
        print("\nAvailable pass types:")
        print("  (r)andom - Writes random data to the disk")
        print("  (z)eros  - Writes zeros to the disk")
        print("  (o)nes   - Writes binary ones (0xFF) to the disk")
        print("  (s)tring - Repeats a specified text string across the disk")
        print("  (f)ile   - Repeats the contents of a file across the disk")
        
        pass_type = input("\nChoose a pass type to add (r, z, o, s, f), or type 'start' to execute once, or 'loop' to repeat: ").strip().lower()
        
        if pass_type == "start" or pass_type == "loop":
            return passes, pass_type == "loop"
        elif pass_type == "r":
            pass_type = "random"
        elif pass_type == "z":
            pass_type = "zeros"
        elif pass_type == "o":
            pass_type = "ones"
        elif pass_type == "s":
            pass_type = "string"
        elif pass_type == "f":
            pass_type = "file"
        else:
            print("Invalid choice. Please enter one of the letters (r, z, o, s, f) or 'start'/'loop' to proceed.")
            continue
        
        if pass_type == "string":
            content = input("Enter a string to write to disk: ").strip()
        elif pass_type == "file":
            content = input("Enter the path to the source file: ").strip()
            if not os.path.isfile(content):
                print("Invalid file path. Please enter a valid file.")
                continue
        else:
            content = None

        block_size, count = input("Enter block size and count separated by a space (or press Enter for default 1M block size and fill disk): ").strip().split() or ("1M", None)
        
        passes.append({"type": pass_type, "content": content, "block_size": block_size, "count": count})
        
        clear_terminal()
        print(f"\nCurrent Pass Schema for drive: {device}")
        for i, p in enumerate(passes, start=1):
            content_display = ""
            if p["type"] == "string":
                content_display = f" (String: {p['content'][:24]}...)"
            elif p["type"] == "file":
                content_display = f" (File: {p['content']})"
            count_display = f", Count: {p['count']}" if p["count"] else ""
            print(f"{i}. Type: {p['type'].capitalize()}, Block Size: {p['block_size']}{count_display}{content_display}")

def main():
    clear_terminal()
    print("Multi-Pass Disk Preparation Script\n")

    if os.geteuid() != 0:
        print("This script requires elevated privileges. Please run with sudo.")
        sys.exit(1)

    device = input("Enter the destination device (e.g., /dev/diskX): ").strip()

    passes, loop_mode = configure_passes(device)

    proceed = input("\nProceed with the above schema? (y/n): ").strip().lower()
    if proceed != 'y':
        print("Exiting without changes.")
        sys.exit(1)

    while True:
        for i, pass_info in enumerate(passes, start=1):
            print(f"\nRunning Pass {i}: Type: {pass_info['type'].capitalize()}, Block Size: {pass_info['block_size']}, Count: {pass_info['count'] or 'until full'}")
            perform_pass(pass_info, device)
        if not loop_mode:
            break

    print("\nDisk preparation completed.")

if __name__ == "__main__":
    main()
