import sys
import struct

def convert_hex_to_bin(input_file, output_file):
    with open(input_file, 'r') as f:
        lines = f.readlines()

    # Skip the first two lines (version info)
    if len(lines) < 3:
        print("Error: Input file too short. Expected at least 3 lines.")
        return

    print(f"Header 1: {lines[0].strip()}")
    print(f"Header 2: {lines[1].strip()}")

    # Concatenate the remaining lines (which contain the hex string)
    hex_data = "".join(line.strip() for line in lines[2:])
    
    # Check if hex_data length is even
    if len(hex_data) % 2 != 0:
        print("Warning: Hex data length is not even. Truncating last character.")
        hex_data = hex_data[:-1]

    try:
        binary_data = bytes.fromhex(hex_data)
        with open(output_file, 'wb') as f:
            f.write(binary_data)
        print(f"Successfully converted {input_file} to {output_file}")
    except ValueError as e:
        print(f"Error converting hex to binary: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python convert_coredump.py <input.hex> <output.bin>")
    else:
        convert_hex_to_bin(sys.argv[1], sys.argv[2])
