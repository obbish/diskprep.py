import os
import sys
import subprocess
import signal
import shutil
import io
import pty

class TempFileManager:
    def __init__(self):
        self.temp_files = []

    def add_temp_file(self, file_obj):
        """Track an in-memory file object for cleanup."""
        self.temp_files.append(file_obj)

    def remove_temp_files(self):
        """Clear all tracked in-memory file objects."""
        for temp_file in self.temp_files:
            temp_file.close()
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

def execute_command(command, input_data):
    """Run the dd command with a PTY to display real-time output and handle 'disk full' messages."""
    master_fd, slave_fd = pty.openpty()  # Create a pseudo-terminal
    
    try:
        # Start the dd process, linking stdout and stderr to the PTY
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=slave_fd, stderr=slave_fd, text=True)
        
        # Feed the in-memory data to dd’s stdin in 1MB chunks
        while True:
            chunk = input_data.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            process.stdin.write(chunk)
            process.stdin.flush()

        os.close(slave_fd)  # Close slave end after writing is done

        # Read and display real-time output from the PTY (dd’s progress)
        while True:
            output = os.read(master_fd, 1024).decode()  # Read from PTY in 1KB chunks
            if not output:
                break
            print(output, end='', flush=True)

        process.wait()
        return process.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Unexpected error: {e}")
        raise
    finally:
        os.close(master_fd)  # Ensure PTY master is closed

def generate_temp_source_in_memory(pass_type, content=None, size_mb=64):
    """
    Generates an in-memory file-like object for source data.

    Args:
        pass_type (str): Type of data ('ones' for 0xFF, 'string' for text string).
        content (str): Content for 'string' type, ignored for 'ones'.
        size_mb (int): Size of the buffer in MB (default 64MB).
        
    Returns:
        io.BytesIO: In-memory file object containing the source data.
    """
    size_bytes = size_mb * 1024 * 1024  # Convert MB to bytes
    
    if pass_type == "ones":
        # Create a 64MB buffer of 0xFF bytes for "ones"
        buffer = io.BytesIO(b"\xFF" * size_bytes)
    elif pass_type == "string" and content:
        # For strings, repeat the encoded content to fill 64MB
        encoded_content = content.encode()
        repeats_needed = size_bytes // len(encoded_content)
        buffer = io.BytesIO(encoded_content * repeats_needed)
    else:
        raise ValueError("Unsupported pass type or missing content for 'string' pass.")

    temp_file_manager.add_temp_file(buffer)
    buffer.seek(0)  # Reset pointer to the start
    return buffer

def path_source(pass_type, device, block_size, count=None, content=None):
    """Constructs the dd command with in-memory input data."""
    temp_file = generate_temp_source_in_memory(pass_type, content)
    if not temp_file:
        return None

    # Prepare dd command with the in-memory input data
    if count:
        return ["dd", f"if=/dev/stdin", f"of={device}", f"bs={block_size}", f"count={count}", "status=progress"], temp_file
    else:
        return ["dd", f"if=/dev/stdin", f"of={device}", f"bs={block_size}", "status=progress"], temp_file

def perform_pass(pass_info, device):
    command, input_data = path_source(pass_info["type"], device, pass_info["block_size"], pass_info.get("count"), pass_info.get("content"))
    if command:
        return execute_command(command, input_data)
    return False

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
        
        pass_type = input("\nChoose a pass type to add (r, z, o, s), or type 'start' to execute once, or 'loop' to repeat: ").strip().lower()
        
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
        else:
            print("Invalid choice. Please enter one of the letters (r, z, o, s) or 'start'/'loop' to proceed.")
            continue
        
        content = input("Enter a string to write to disk: ").strip() if pass_type == "string" else None
        block_size, count = input("Enter block size and count separated by a space (or press Enter for default 1M block size and fill disk): ").strip().split() or ("1M", None)
        passes.append({"type": pass_type, "content": content, "block_size": block_size, "count": count})
        
        clear_terminal()
        print(f"\nCurrent Pass Schema for drive: {device}")
        for i, p in enumerate(passes, start=1):
            content_display = f" (String: {p['content'][:24]}...)" if p["type"] == "string" else ""
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
            if perform_pass(pass_info, device):
                print("Disk is full. Exiting.")
                return  # Exit if the disk is full

        if not loop_mode:
            break  # Exit after one iteration if not in loop mode

        print("\nRepeating schema in loop mode...")

    print("\nDisk preparation completed.")

if __name__ == "__main__":
    main()
