"""A small Tkinter window that shows a query in every SQL dialect."""
import tkinter as tk
from tkinter import ttk

from .converter import convert_all
from .detector import DIALECTS, DISPLAY_NAMES, detect_dialect, normalize_dialect

_AUTO = "Auto-detect"
_MONO = ("Consolas", 11)


def show(query: str = "") -> None:
    """Open the window. Optionally pre-fill it with `query`."""
    root = tk.Tk()
    root.title("sqlflip - SQL dialect detector & converter")
    root.geometry("920x680")
    root.minsize(700, 520)

    main = ttk.Frame(root, padding=10)
    main.pack(fill="both", expand=True)

    # ---- input --------------------------------------------------------------
    ttk.Label(main, text="Paste your SQL query:").pack(anchor="w")
    input_box = tk.Text(main, height=8, font=_MONO, wrap="word", undo=True)
    input_box.pack(fill="x", pady=(2, 8))
    input_box.insert("1.0", query)

    # ---- controls -----------------------------------------------------------
    controls = ttk.Frame(main)
    controls.pack(fill="x")
    ttk.Label(controls, text="Source dialect:").pack(side="left")
    source_var = tk.StringVar(value=_AUTO)
    ttk.Combobox(
        controls, textvariable=source_var, state="readonly", width=20,
        values=[_AUTO] + [DISPLAY_NAMES[d] for d in DIALECTS],
    ).pack(side="left", padx=6)

    status_var = tk.StringVar(value="Paste a query and click 'Detect & Convert'.")
    ttk.Label(main, textvariable=status_var, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 4))

    # ---- one tab per dialect --------------------------------------------------
    notebook = ttk.Notebook(main)
    notebook.pack(fill="both", expand=True)
    outputs, note_vars = {}, {}

    def make_copy(d):
        def _copy():
            root.clipboard_clear()
            root.clipboard_append(outputs[d].get("1.0", "end").strip())
        return _copy

    for d in DIALECTS:
        tab = ttk.Frame(notebook, padding=6)
        notebook.add(tab, text=DISPLAY_NAMES[d])
        box = tk.Text(tab, font=_MONO, wrap="word", state="disabled", bg="#f6f6f6")
        box.pack(fill="both", expand=True)
        outputs[d] = box
        note_vars[d] = tk.StringVar()
        ttk.Label(tab, textvariable=note_vars[d], foreground="#a05a00",
                  wraplength=840, justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Button(tab, text="Copy", command=make_copy(d)).pack(anchor="e", pady=(6, 0))

    # ---- actions -----------------------------------------------------------
    def run():
        q = input_box.get("1.0", "end").strip()
        if not q:
            status_var.set("Please paste a SQL query first.")
            return
        detection = detect_dialect(q)
        chosen = source_var.get()
        if chosen == _AUTO:
            source = detection.dialect
            status_var.set("Detected: %s" % detection)
        else:
            source = next(d for d in DIALECTS if DISPLAY_NAMES[d] == chosen)
            status_var.set("Using source dialect: %s" % chosen)

        results = convert_all(q, source)
        for i, d in enumerate(DIALECTS):
            box = outputs[d]
            box.config(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", results[d].sql)
            box.config(state="disabled")
            note_vars[d].set("\n".join("! " + n for n in results[d].notes))
            title = DISPLAY_NAMES[d] + ("  (source)" if d == source else "")
            notebook.tab(i, text=title)
        notebook.select(DIALECTS.index(source))

    def clear():
        input_box.delete("1.0", "end")
        status_var.set("Paste a query and click 'Detect & Convert'.")

    ttk.Button(controls, text="Detect & Convert", command=run).pack(side="left", padx=6)
    ttk.Button(controls, text="Clear", command=clear).pack(side="left")

    if query.strip():
        run()
    root.mainloop()


def main() -> None:
    show()


if __name__ == "__main__":
    main()
