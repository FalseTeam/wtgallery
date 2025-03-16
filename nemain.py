import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageFile, ImageSequence
from main import search_images_by_text, load_image_embeddings

ImageFile.LOAD_TRUNCATED_IMAGES = True


def open_image_in_viewer(image_path):
    try:
        if os.name == "nt":  # Windows
            subprocess.run(["explorer", image_path], check=True)
        elif os.name == "posix":  # macOS or Linux
            subprocess.run(["xdg-open", image_path], check=True)
        else:
            print("Unsupported OS. Unable to open the image in the default image viewer.")
    except subprocess.CalledProcessError as e:
        print(f"Error opening image '{image_path}' in the default image viewer: {e}")


def on_image_click(event):
    image_path = event.widget.image_path
    open_image_in_viewer(image_path)


def show_overlay():
    global overlay
    overlay = tk.Frame(root, bg="grey")
    overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
    overlay_label = tk.Label(overlay, text="Loading", bg="grey", fg="white", font=("Helvetica", 24))
    overlay_label.place(relx=0.5, rely=0.25, anchor='center')
    global animating
    animating = True
    animate_loading_dots(overlay_label)


def animate_loading_dots(label):
    global animating
    if not animating:
        return
    text = label.cget("text")
    if text.count('.') < 3:
        label.configure(text=text + '.')
    else:
        label.configure(text="Loading")
    root.after(500, animate_loading_dots, label)


def hide_overlay():
    global overlay
    global animating
    animating = False
    overlay.destroy()


def search_and_update_gallery(event=None):
    show_overlay()  # Show the overlay at the beginning of the search
    root.update_idletasks()  # Force the window to update, so the overlay is actually displayed

    # Start the search in a separate thread
    search_thread = threading.Thread(target=perform_search)
    search_thread.start()


def perform_search():
    text_query = query_entry.get()
    top_k_value = int(top_k_combobox.get())

    sorted_images = search_images_by_text(loaded_image_embeddings, text_query)
    print("\nSearch complete")

    # Update the gallery in the main thread
    root.after(0, create_gallery, frame_container, sorted_images[:top_k_value])
    root.after(0, canvas.yview_moveto, 0)
    root.after(0, hide_overlay)  # Hide the overlay once the search is complete


def create_gallery(frame_container, sorted_images):
    # Remove existing widgets from the frame
    for widget in frame_container.winfo_children():
        widget.destroy()

    num_columns = 4
    for i, (image_path, similarity_score) in enumerate(sorted_images):
        create_gallery_cell(frame_container, i, image_path, similarity_score, num_columns)


def on_mousewheel(event):
    canvas.yview_scroll(-1 * (event.delta // 120), "units")


def on_resize(event):
    canvas_width = canvas.winfo_width()
    num_columns = max(1, canvas_width // 220)
    for i, child in enumerate(frame_container.winfo_children()):
        child.grid(row=i // num_columns, column=i % num_columns, padx=10, pady=5)
    canvas.configure(scrollregion=canvas.bbox("all"))


def create_gallery_cell(frame_container, i, image_path, similarity_score, num_columns):
    cell = ttk.Frame(frame_container)  # Individual cell for each image
    cell.grid(row=i // num_columns, column=i % num_columns, padx=10, pady=5)

    image = Image.open(image_path)
    image.thumbnail((200, 200))
    photo = ImageTk.PhotoImage(image)

    label = ttk.Label(cell, image=photo)
    label.image = photo
    label.grid(row=0, column=0)
    label.image_path = image_path
    label.bind("<Button-1>", on_image_click)

    image_name = os.path.splitext(os.path.basename(image_path))[0]
    ttk.Label(cell, text=image_name, wraplength=200).grid(row=1, column=0)
    ttk.Label(cell, text=f"Similarity Score: {similarity_score:.4f}").grid(row=2, column=0)

    if image.format == 'GIF':
        max_size = (200, 200)
        resize_ratio = min(max_size[0] / image.width, max_size[1] / image.height)
        resize_size = (int(image.width * resize_ratio), int(image.height * resize_ratio))
        canvas_size = (max_size[0], max_size[1])
        resized_frames = [Image.new("RGBA", canvas_size) for _ in ImageSequence.Iterator(image)]
        for original_frame, frame_canvas in zip(ImageSequence.Iterator(image), resized_frames):
            frame_resized = original_frame.resize(resize_size, Image.LANCZOS)
            frame_canvas.paste(frame_resized, (
                (canvas_size[0] - frame_resized.width) // 2, (canvas_size[1] - frame_resized.height) // 2))
        animated_gif = ImageTk.PhotoImage(resized_frames[0])
        label.configure(image=animated_gif)
        label.image = animated_gif

        def update_gif(frame_number):
            nonlocal animated_gif
            animated_gif.paste(resized_frames[frame_number])
            root.after(100, update_gif, (frame_number + 1) % len(resized_frames))

        root.after(0, update_gif, 1)


loaded_image_embeddings = load_image_embeddings("tg_fox_dump_large14_cpu_batch_768.pt")

root = tk.Tk()
root.geometry("1600x800")
root.title("Image Gallery")

query_frame = ttk.Frame(root)
query_frame.grid(row=0, column=0, columnspan=5, sticky="ew")
query_frame.grid_rowconfigure(0, weight=1)
query_frame.grid_columnconfigure(1, weight=1)

query_label = ttk.Label(query_frame, text="Query:")
query_label.grid(row=0, column=0)
query_entry = ttk.Entry(query_frame)
query_entry.grid(row=0, column=1, sticky="ew")
query_entry.bind('<Return>', search_and_update_gallery)  # Binding the Enter key to the search

top_k_label = ttk.Label(query_frame, text="Top K:")
top_k_label.grid(row=0, column=2)
# noinspection PyTypeChecker
top_k_combobox = ttk.Combobox(query_frame, values=[21, 28, 35, 42, 49, 56, 63, 70, 77, 84, 91, 98], width=5)
top_k_combobox.set(49)
top_k_combobox.grid(row=0, column=3)

search_button = ttk.Button(query_frame, text="Search", command=search_and_update_gallery)
search_button.grid(row=0, column=4, padx=5)

canvas = tk.Canvas(root)
scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
frame_container = ttk.Frame(canvas)  # Frame for holding all images

canvas.grid(row=1, column=0, columnspan=5, sticky="nsew")
scrollbar.grid(row=1, column=5, sticky="ns")
canvas.configure(yscrollcommand=scrollbar.set)
canvas.create_window((0, 0), window=frame_container, anchor="nw")
canvas.bind_all("<MouseWheel>", on_mousewheel)  # Binding mouse wheel for scrolling

root.grid_rowconfigure(1, weight=1)
root.grid_columnconfigure(0, weight=1)

root.bind("<Configure>", on_resize)

root.mainloop()
