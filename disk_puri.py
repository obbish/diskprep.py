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

def clear_terminal():
    """Clear the terminal screen."""
    os.system('clear' if os.name == 'posix' else 'cls')

def stream_source(pass_type, device, block_size, count=None):
    """Build command for live data sources like random and zero."""
    if pass_type == "random":
        command = f"dd if=/dev/urandom of={device} bs={block_size} status=progress"
    elif pass_type == "zeros":
        command = f"dd if=/dev/zero of={device} bs={block_size} status=progress"
    
    if count:
        command += f" count={count}"
    
    return command

def path_source(pass_type, device, block_size, count=None, content=None):
    """Build command for file-based data sources like ones, string, and file."""
    temp_file = None
    
    if pass_type == "ones":
        temp_file = "ones_source.tmp"
        if not os.path.isfile(temp_file):
            with open(temp_file, "wb") as f:
                f.write(b"\xFF" * (1024 * 1024 * 256))  # 256MB of 0xFF bytes
        temp_files.append(temp_file)
    
    elif pass_type == "string":
        temp_file = "string_source.tmp"
        if not os.path.isfile(temp_file):
            with open(temp_file, "wb") as f:
                for _ in range(256):  # Fill 256MB with repeated string
                    f.write(content.encode() * (1024 * 1024 // len(content)))
        temp_files.append(temp_file)
    
    elif pass_type == "file":
        temp_file = content
        if not os.path.isfile(temp_file):
            print(f"Error: File not found at {temp_file}. Skipping this pass.")
            return None
    
    # Construct the command
    if count:
        command = f"dd if={temp_file} of={device} bs={block_size} count={count} status=progress"
    else:
        command = f"while :; do cat {temp_file}; done | dd of={device} bs={block_size} status=progress"
    
    return command

def execute_command(command):
    """Run the dd command, display real-time output, and handle 'disk full' message."""
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Process output in real-time
        for line in process.stderr:
            if "No space left on device" in line:
                print("\nDisk full; moving to the next pass.")
                process.terminate()
                break
            print(line, end='')  # Real-time feedback for each line

        process.wait()  # Ensure the process completes fully
    except subprocess.CalledProcessError as e:
        if "No space left on device" in e.stderr:
            print("Disk full; moving to the next pass.")
        else:
            print(f"Unexpected error: {e}")
            raise  # Re-raise unexpected errors

def perform_pass(pass_info, device):
    """Prepare and execute a pass with centralized error handling."""
    pass_type = pass_info["type"]
    block_size = pass_info["block_size"]
    count = pass_info.get("count")
    content = pass_info.get("content")

    # Build the command based on pass type
    if pass_type in ["random", "zeros"]:
        command = stream_source(pass_type, device, block_size, count)
    elif pass_type in ["ones", "string", "file"]:
        command = path_source(pass_type, device, block_size, count, content)
    
    # Execute the command if it was successfully built
    if command:
        execute_command(command)

def configure_passes(device):
    """Allow users to create their own pass schema with real-time schema display."""
    passes = []
    clear_terminal()
    print(f"Create your custom pass schema for drive: {device}\n")
    
    while True:
        # Enhanced pass type prompt with descriptions and line breaks for clarity
        print("\nAvailable pass types:")
        print("  (r)andom - Writes random data to the disk")
        print("  (z)eros  - Writes zeros to the disk")
        print("  (o)nes   - Writes binary ones (0xFF) to the disk")
        print("  (s)tring - Repeats a specified text string across the disk")
        print("  (f)ile   - Repeats the contents of a file across the disk")
        
        pass_type = input("\nChoose a pass type to add (r, z, o, s, f), or type 'start' to execute once, or 'loop' to repeat: ").strip().lower()
        
        # Match user input to pass types
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
        
        # Prompt for content if necessary
        if pass_type == "string":
            content = input("Enter the string to fill the disk with: ").strip()
        elif pass_type == "file":
            content = input("Enter the path to the source file: ").strip()
            if not os.path.isfile(content):
                print("Invalid file path. Please enter a valid file.")
                continue
        else:
            content = None  # No content required for random, zeros, and ones

        # Prompt for block size and count with defaults
        block_size, count = input("Enter block size and count separated by a space (or press Enter for default 1M block size and fill disk): ").strip().split() or ("1M", None)
        
        # Add the pass with type, content, block size, and count
        passes.append({"type": pass_type, "content": content, "block_size": block_size, "count": count})
        
        # Clear terminal and print the updated schema after each addition for clarity
        clear_terminal()
        print(f"\nCurrent Pass Schema for drive: {device}")
        for i, p in enumerate(passes, start=1):
            content_display = ""
            if p["type"] == "string":
                content_display = f" (String: {p['content'][:24]}...)"  # Show first 24 characters
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

    # Configure passes
    passes, loop_mode = configure_passes(device)

    # Confirm before proceeding
    proceed = input("\nProceed with the above schema? (y/n): ").strip().lower()
    if proceed != 'y':
        print("Exiting without changes.")
        sys.exit(1)

    # Run each pass
    while True:
        for i, pass_info in enumerate(passes, start=1):
            print(f"\nRunning Pass {i}: Type: {pass_info['type'].capitalize()}, Block Size: {pass_info['block_size']}, Count: {pass_info['count'] or 'until full'}")
            perform_pass(pass_info, device)
        if not loop_mode:
            break

    print("\nDisk preparation completed.")

if __name__ == "__main__":
    main()
