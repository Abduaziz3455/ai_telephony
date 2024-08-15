import os
from pydub import AudioSegment


def convert_mp4a_to_mp3_and_rename(folder_path):
    # Ensure ffmpeg is available
    AudioSegment.ffmpeg = "ffmpeg"

    files = [f for f in os.listdir(folder_path) if f.endswith(".m4a")]
    files.sort()  # Optional: Sort files if you want to maintain a specific order
    print(len(files))
    for idx, filename in enumerate(files, start=1):
        mp4a_path = os.path.join(folder_path, filename)
        mp3_path = os.path.join(folder_path, f"{idx}.mp3")

        # Convert mp4a to mp3
        audio = AudioSegment.from_file(mp4a_path, format="mp4")
        audio.export(mp3_path, format="mp3")

        # Delete the original mp4a file
        os.remove(mp4a_path)
        print(f"Converted and renamed: {mp4a_path} to {mp3_path}")


if __name__ == "__main__":
    folder_path = "mp4a/"  # Replace with your folder path if different
    convert_mp4a_to_mp3_and_rename(folder_path)
