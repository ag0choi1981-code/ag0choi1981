from __future__ import annotations

import csv
import threading
from pathlib import Path
from tkinter import END, BOTH, X, filedialog, messagebox, ttk
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

from news_comment_analyzer import analyze_news_url


class NewsCommentDesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("News Comment Analyzer")
        self.root.geometry("980x700")

        self.comments: list[dict[str, str]] = []

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=X)

        ttk.Label(top, text="News URL").pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(top, textvariable=self.url_var, width=90)
        self.url_entry.pack(side=tk.LEFT, padx=8, fill=X, expand=True)
        self.url_entry.insert(0, "https://")

        self.analyze_btn = ttk.Button(top, text="Analyze", command=self.on_analyze)
        self.analyze_btn.pack(side=tk.LEFT)

        status_frame = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        status_frame.pack(fill=X)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)

        main = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        main.pack(fill=BOTH, expand=True, padx=10, pady=10)

        article_frame = ttk.LabelFrame(main, text="Article Analysis", padding=8)
        main.add(article_frame, weight=2)

        self.article_text = ScrolledText(article_frame, wrap=tk.WORD, height=12)
        self.article_text.pack(fill=BOTH, expand=True)

        comment_frame = ttk.LabelFrame(main, text="Comments", padding=8)
        main.add(comment_frame, weight=3)

        cols = ("id", "sentiment", "comment")
        self.tree = ttk.Treeview(comment_frame, columns=cols, show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("sentiment", text="Sentiment")
        self.tree.heading("comment", text="Comment")
        self.tree.column("id", width=60, anchor="center")
        self.tree.column("sentiment", width=110, anchor="center")
        self.tree.column("comment", width=760, anchor="w")

        yscroll = ttk.Scrollbar(comment_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side=tk.LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill=X)

        self.save_btn = ttk.Button(bottom, text="Save Comments CSV", command=self.save_csv)
        self.save_btn.pack(side=tk.RIGHT)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.root.update_idletasks()

    def on_analyze(self) -> None:
        url = self.url_var.get().strip()
        if not url.startswith(("http://", "https://")):
            messagebox.showerror("Invalid URL", "URL must start with http:// or https://")
            return

        self.analyze_btn.configure(state=tk.DISABLED)
        self.set_status("Analyzing...")
        threading.Thread(target=self._analyze_worker, args=(url,), daemon=True).start()

    def _analyze_worker(self, url: str) -> None:
        try:
            result = analyze_news_url(url)
            self.root.after(0, self._update_result, result)
        except Exception as exc:
            self.root.after(0, self._handle_error, exc)

    def _handle_error(self, exc: Exception) -> None:
        self.analyze_btn.configure(state=tk.NORMAL)
        self.set_status("Failed")
        messagebox.showerror("Analysis Failed", str(exc))

    def _update_result(self, result) -> None:
        self.analyze_btn.configure(state=tk.NORMAL)
        self.set_status(f"Done - {result.total_comments} comments")

        article_lines = [
            f"Domain: {result.domain}",
            f"Title: {result.title}",
            f"Article length: {len(result.article_text)} chars",
            f"Summary: {result.article_summary or 'N/A'}",
            "",
            "Article keywords: " + (", ".join(result.article_keywords) if result.article_keywords else "N/A"),
            "Comment keywords: " + (", ".join(result.comment_keywords) if result.comment_keywords else "N/A"),
            (
                "Sentiment counts: "
                f"positive={result.sentiment_counts['positive']}, "
                f"negative={result.sentiment_counts['negative']}, "
                f"neutral={result.sentiment_counts['neutral']}"
            ),
        ]
        self.article_text.delete("1.0", END)
        self.article_text.insert(END, "\n".join(article_lines))

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.comments = result.comments
        for row in self.comments:
            self.tree.insert("", END, values=(row["id"], row["sentiment"], row["comment"]))

    def save_csv(self) -> None:
        if not self.comments:
            messagebox.showinfo("No Data", "No comments to save yet.")
            return

        path = filedialog.asksaveasfilename(
            title="Save comments CSV",
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv")],
            initialfile="comments.csv",
        )
        if not path:
            return

        out = Path(path)
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "comment", "sentiment"])
            for row in self.comments:
                writer.writerow([row["id"], row["comment"], row["sentiment"]])

        messagebox.showinfo("Saved", f"Saved: {out}")


def main() -> None:
    root = tk.Tk()
    NewsCommentDesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

