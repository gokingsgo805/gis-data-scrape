# gis-data-scrape

Public-sourced data scraped geospatial info → visual maps with dropdown info.

---

## `organize_gis_files.py` – Pair KMZ / GeoJSON files into separate repos

This script scans a directory for `.kmz` and `.geojson` files, pairs them up
(matching by base filename first, then by order), and copies each pair into its
own subdirectory with a fresh git repository — ready to push to GitHub as a
separate repo.

### Requirements

- Python 3.8+
- `git` available on your `PATH`

### Usage

```bash
python organize_gis_files.py <source_dir> [--output-dir <out_dir>]
```

| Argument | Description |
|---|---|
| `source_dir` | Path to the folder containing your `.kmz` and `.geojson` files |
| `--output-dir` | Where to write the paired sub-repos (default: `./gis-repos`) |

### Windows example

```powershell
python organize_gis_files.py "C:\Users\Cobiwan Kenobi" --output-dir "C:\Users\Cobiwan Kenobi\gis-repos"
```

### WSL / macOS / Linux example

```bash
python organize_gis_files.py "/mnt/c/Users/Cobiwan Kenobi" --output-dir ./gis-repos
```

### What happens

1. All `.kmz` and `.geojson` files in the source directory are discovered.
2. Files are **paired by matching base name** (e.g. `parks.kmz` ↔ `parks.geojson`).
3. Any remaining unmatched files are **paired in alphabetical order**.
4. Each pair is copied into `<output-dir>/<pair-name>/` and a `README.md` is generated.
5. `git init` + initial commit is run inside every sub-directory.

### After the script runs

For each generated sub-directory, create a new GitHub repository and push:

```bash
cd gis-repos/<pair-name>
git remote add origin https://github.com/<your-username>/<pair-name>.git
git branch -M main   # rename to main if git defaulted to master
git push -u origin main
```
