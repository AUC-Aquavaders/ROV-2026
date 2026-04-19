import tkinter as tk
from tkinter import ttk, messagebox

# --- Fixed species list ---
DEFAULT_SPECIES = [
    "Snow Crab (Chionecetes opilio)",
    "Acadian Hermit Crab (Pagarus acadianus)",
    "Western Atlantic Hairy Hermit Crab (Pagarus arcuatus)",
    "European Green Crab (Carcinus maenas)",
    "Rock Crab (Cancer pagurus)",
    "Jonah Crab (Cancer borealis)",
    "Spiny Sunstar (Crossaster papposus)",
    "Sea Urchin (Stronglyocentrotus droebachiensis)",
    "Boreal Sea Star (Boreal asterias)",
    "Daisy Brittle Star (Ophiopholis aculeata)",
]

class FrequencyAnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Species Frequency Analysis – Holyrood Subsea Observatory")
        self.root.configure(bg="#1a1a2e")
        self.root.geometry("1150x650")
        
        self.entries = []        
        self.result_rows = []    
        self._build_ui()

    def _build_ui(self):
        # Header Section
        header = tk.Frame(self.root, bg="#16213e", height=80)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="📊 Species Frequency Analysis",
                 font=("Segoe UI", 18, "bold"),
                 bg="#16213e", fg="#e94560").pack(side=tk.LEFT, padx=30, pady=20)
        
        tk.Label(header, text="Holyrood Subsea Observatory",
                 font=("Segoe UI", 10, "italic"),
                 bg="#16213e", fg="#a8a8b3").pack(side=tk.RIGHT, padx=30, pady=25)

        # Main Container
        main_frame = tk.Frame(self.root, bg="#1a1a2e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # LEFT COLUMN: Data Entry
        left_col = tk.Frame(main_frame, bg="#1a1a2e")
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))

        tk.Label(left_col, text="Step 1: Enter Observations", font=("Segoe UI", 12, "bold"),
                 bg="#1a1a2e", fg="#00d2ff").pack(anchor=tk.W, pady=(0, 10))

        entry_container = tk.Frame(left_col, bg="#16213e", bd=1, relief=tk.RIDGE)
        entry_container.pack(padx=2, pady=2)

        # Table Headers (Left)
        headers = ["#", "Species Name", "Count"]
        widths = [4, 35, 10]
        for idx, h in enumerate(headers):
            tk.Label(entry_container, text=h, font=("Segoe UI", 9, "bold"),
                     bg="#0f3460", fg="white", width=widths[idx], pady=5).grid(row=0, column=idx, sticky=tk.NSEW)

        # Row Generation
        for i, species in enumerate(DEFAULT_SPECIES):
            bg_color = "#16213e" if i % 2 == 0 else "#1a1a2e"
            
            tk.Label(entry_container, text=str(i+1), bg=bg_color, fg="#a8a8b3", pady=5).grid(row=i+1, column=0, sticky=tk.NSEW)
            tk.Label(entry_container, text=species, bg=bg_color, fg="#e2e2e2", anchor=tk.W, padx=10).grid(row=i+1, column=1, sticky=tk.NSEW)
            
            var = tk.StringVar(value="0")
            ent = tk.Entry(entry_container, textvariable=var, bg="#0f3460", fg="white", 
                           insertbackground="white", width=8, justify=tk.CENTER, relief=tk.FLAT)
            ent.grid(row=i+1, column=2, padx=5, pady=2, ipady=3)
            self.entries.append((species, var))

        # Control Buttons
        btn_frame = tk.Frame(left_col, bg="#1a1a2e")
        btn_frame.pack(fill=tk.X, pady=20)
        
        # Updated Calculate Button
        tk.Button(btn_frame, text="  📊  Run Analysis  ",
                command=self._calculate,
                # ... rest of your styling ...
                ).pack(side=tk.LEFT, padx=6)

        # Updated Reset Button
        tk.Button(btn_frame, text="  🔄  Clear All  ",
                command=self._reset,
                # ... rest of your styling ...
                ).pack(side=tk.LEFT, padx=6)

        # RIGHT COLUMN: Results Display
        right_col = tk.Frame(main_frame, bg="#1a1a2e")
        right_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(right_col, text="Step 2: Analysis Results", font=("Segoe UI", 12, "bold"),
                 bg="#1a1a2e", fg="#00d2ff").pack(anchor=tk.W, pady=(0, 10))

        self.res_table = tk.Frame(right_col, bg="#16213e", bd=1, relief=tk.RIDGE)
        self.res_table.pack(fill=tk.X)

        # Results Headers
        res_headers = ["Species", "Observed", "Frequency (%)"]
        res_widths = [35, 12, 15]
        for idx, h in enumerate(res_headers):
            tk.Label(self.res_table, text=h, font=("Segoe UI", 9, "bold"),
                     bg="#0f3460", fg="white", width=res_widths[idx], pady=5).grid(row=0, column=idx, sticky=tk.NSEW)

        # Result Row Placeholders
        for i in range(len(DEFAULT_SPECIES)):
            bg_color = "#16213e" if i % 2 == 0 else "#1a1a2e"
            l_name = tk.Label(self.res_table, text="—", bg=bg_color, fg="#555555", anchor=tk.W, padx=10, pady=5)
            l_count = tk.Label(self.res_table, text="—", bg=bg_color, fg="#555555")
            l_pct = tk.Label(self.res_table, text="—", bg=bg_color, fg="#555555")
            
            l_name.grid(row=i+1, column=0, sticky=tk.NSEW)
            l_count.grid(row=i+1, column=1, sticky=tk.NSEW)
            l_pct.grid(row=i+1, column=2, sticky=tk.NSEW)
            self.result_rows.append((l_name, l_count, l_pct))

        # Totals Row
        self.tot_name = tk.Label(self.res_table, text="TOTAL", bg="#0f3460", fg="white", font=("Segoe UI", 10, "bold"), anchor=tk.W, padx=10, pady=8)
        self.tot_count = tk.Label(self.res_table, text="0", bg="#0f3460", fg="white", font=("Segoe UI", 10, "bold"))
        self.tot_pct = tk.Label(self.res_table, text="0.00%", bg="#0f3460", fg="white", font=("Segoe UI", 10, "bold"))
        
        self.tot_name.grid(row=12, column=0, sticky=tk.NSEW, pady=(5,0))
        self.tot_count.grid(row=12, column=1, sticky=tk.NSEW, pady=(5,0))
        self.tot_pct.grid(row=12, column=2, sticky=tk.NSEW, pady=(5,0))

    def _calculate(self):
        try:
            raw_data = []
            total = 0
            for name, var in self.entries:
                val = int(var.get())
                if val < 0: raise ValueError
                raw_data.append(val)
                total += val

            if total == 0:
                messagebox.showwarning("No Data", "Total count is zero. Please enter at least one observation.")
                return

            for i, count in enumerate(raw_data):
                percentage = (count / total) * 100
                name_lbl, count_lbl, pct_lbl = self.result_rows[i]
                
                name_lbl.config(text=DEFAULT_SPECIES[i], fg="#e2e2e2")
                count_lbl.config(text=str(count), fg="#e2e2e2")
                pct_lbl.config(text=f"{percentage:.2f}%", fg="#00e5a0")

            self.tot_count.config(text=str(total))
            self.tot_pct.config(text="100.00%")

        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid non-negative integers.")

    def _reset(self):
        for _, var in self.entries:
            var.set("0")
        for n, c, p in self.result_rows:
            n.config(text="—", fg="#555555")
            c.config(text="—", fg="#555555")
            p.config(text="—", fg="#555555")
        self.tot_count.config(text="0")
        self.tot_pct.config(text="0.00%")

if __name__ == "__main__":
    root = tk.Tk()
    app = FrequencyAnalysisApp(root)
    root.mainloop()