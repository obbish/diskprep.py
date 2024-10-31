import os
import sys
import subprocess
import signal

# Global list to track temporary files for cleanup
temp_files = []

def cleanup(signum, frame):
    """Remove temporary files and exit gracefully."""
    for temp_file in temp_files:
        if os.path.isfile(temp_file):
            os.remove(temp_file)
    print("\nProcess interrupted. Exiting.")
    sys.exit(0)

# Register the cleanup function with SIGINT (Ctrl+C)
signal.signal(signal.SIGINT, cleanup)

def build_command(pass_type, device, block_size, count=None, content=None):
    """Build the dd command based on the pass type and source data."""
    command = ""
    temp_file = None
    
    if pass_type == "random":
        command = f"dd if=/dev/urandom of={device} bs={block_size} status=progress"
    elif pass_type == "zeros":
        command = f"dd if=/dev/zero of={device} bs={block_size} status=progress"
    elif pass_type == "ones":
        temp_file = create_temp_file("ones_source.tmp", b"\xFF" * (1024 * 1024 * 256))
        command = f"dd if={temp_file} of={device} bs={block_size} status=progress"
    elif pass_type == "string":
        temp_file = create_temp_file("string_source.tmp", content.encode() * (1024 * 1024 // len(content)))
        command = f"dd if={temp_file} of={device} bs={block_size} status=progress"
    elif pass_type == "file":
        command = f"dd if={content} of={device} bs={block_size} status=progress"
        
    if count:
        command += f" count={count}"
    
    return command

def create_temp_file(filename, data):
    """Create a temporary file with specified data and return the filename."""
    if not os.path.isfile(filename):
        with open(filename, "wb") as f:
            f.write(data)
        temp_files.append(filename)
    return filename

def execute_command(command):
    """Run the dd command, display real-time output, and handle 'disk full' message."""
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in process.stderr:
            if "No space left on device" in line:
                print("\nDisk full; moving to the next pass.")
                process.terminate()
                break
            print(line, end='')  # Real-time feedback for each line
        process.wait()
    except subprocess.CalledProcessError as e:
        if "No space left on device" in e.stderr:
            print("Disk full; moving to the next pass.")
        else:
            print(f"Unexpected error: {e}")
            raise

def perform_pass(pass_info, device):
    """Prepare and execute a pass with centralized error handling."""
    command = build_command(
        pass_type=pass_info["type"], 
        device=device, 
        block_size=pass_info["block_size"], 
        count=pass_info.get("count"), 
        content=pass_info.get("content")
    )
    if command:
        execute_command(command)

def configure_passes(device):
    """Allow users to create their own pass schema with real-time schema display."""
    passes = []
    print(f"Create your custom pass schema for drive: {device}\n")
    
    while True:
        print("Available pass types:")
        print("  (r)andom - Writes random data to the disk")
        print("  (z)eros  - Writes zeros to the disk")
        print("  (o)nes   - Writes binary ones (0xFF) to the disk")
        print("  (s)tring - Repeats a specified text string across the disk")
        print("  (f)ile   - Repeats the contents of a file across the disk")
        pass_type = input("Choose a pass type to add (r, z, o, s, f), or 'done' to finish: ").strip().lower()

        if pass_type == "done":
            break
        pass_type = {"r": "random", "z": "zeros", "o": "ones", "s": "string", "f": "file"}.get(pass_type)
        
        if not pass_type:
            print("Invalid choice. Please enter (r, z, o, s, f) or 'done'.")
            continue
        
        content = None
        if pass_type == "string":
            content = input("Enter the string to fill the disk with: ").strip()
        elif pass_type == "file":
            content = input("Enter the path to the source file: ").strip()
            if not os.path.isfile(content):
                print("Invalid file path. Please enter a valid file.")
                continue

        bs_count_input = input("Enter block size and count (e.g., '4M 10'), or press Enter for default (1M and until full): ").strip()
        block_size, count = ("1M", None) if not bs_count_input else (bs_count_input.split() + [None])[:2]

        passes.append({"type": pass_type, "content": content, "block_size": block_size, "count": count})

        print(f"\nCurrent Pass Schema for drive: {device}")
        for i, p in enumerate(passes, start=1):
            content_display = f" (String: {p['content'][:24]}...)" if p["type"] == "string" else f" (File: {p['content']})" if p["type"] == "file" else ""
            count_display = f", Count: {p['count']}" if p["count"] else ""
            print(f"{i}. Type: {p['type'].capitalize()}, Block Size: {p['block_size']}{count_display}{content_display}")
    
    return passes

def main():
    print("Multi-Pass Disk Preparation Script")

    if os.geteuid() != 0:
        print("This script requires elevated privileges. Please run with sudo.")
        sys.exit(1)

    device = input("\nEnter the destination device (e.g., /dev/diskX): ")
    passes = configure_passes(device)

    print(f"\nSelected Device: {device}")
    for i, pass_info in enumerate(passes, start=1):
        count_display = f", Count: {pass_info['count']}" if pass_info["count"] else ""
        content_display = f" (String: {pass_info['content'][:24]}...)" if pass_info["type"] == "string" else ""
        print(f"  {i}. Type: {pass_info['type'].capitalize()}, Block Size: {pass_info['block_size']}{count_display}{content_display}")

    if input("\nProceed with the above schema on the selected device? (y/n): ").strip().lower() != 'y':
        print("Exiting without changes.")
        sys.exit(1)

    for i, pass_info in enumerate(passes, start=1):
        print(f"Running Pass {i}: Type: {pass_info['type'].capitalize()}, Block Size: {pass_info['block_size']}, Count: {pass_info['count'] or 'until full'}")
        perform_pass(pass_info, device)

    print("Disk preparation completed.")

if __name__ == "__main__":
    main()
