import tkinter as tk
from PIL import Image, ImageTk, ImageSequence


def create_window(image_path):
    def update_gif(frame_number):
        nonlocal animated_gif
        animated_gif.paste(resized_frames[frame_number])
        root.after(100, update_gif, (frame_number + 1) % len(resized_frames))

    image = Image.open(image_path)

    max_size = (200, 200)
    gif_frames = [frame.copy() for frame in ImageSequence.Iterator(image)]

    # Calculate the ratio for resizing while keeping the aspect ratio
    width_ratio = max_size[0] / image.width
    height_ratio = max_size[1] / image.height
    resize_ratio = min(width_ratio, height_ratio)
    resize_size = (int(image.width * resize_ratio), int(image.height * resize_ratio))

    # Resize each frame using the calculated ratio
    resized_frames = [frame.resize(resize_size, Image.LANCZOS) for frame in gif_frames]

    root = tk.Tk()
    animated_gif = ImageTk.PhotoImage(resized_frames[0])
    label = tk.Label(root, image=animated_gif)
    label.pack()
    root.after(0, update_gif, 1)

    root.mainloop()


create_window('C:\\Users\\edis0n\\Downloads\\Telegram Desktop\\animation (4).gif')
