# HECKTOR Annotation Tool

A napari-based viewer for reviewing and refining head-and-neck tumor (GTVp) and lymph node (GTVn) segmentations on CT/PET. All data is read from and written to a **local folder**.

## Data folder layout

```
<data folder>/
├── ehr.csv                         # optional; "Patient #", "T-stage", "N-stage", ...
├── primary_tumor_validation_tstage.csv   # optional
├── <ID>__CT.nii.gz                 # also accepted: <ID>/<ID>__CT.nii.gz, <ID>_CT.nii.gz, ...
├── <ID>__PT.nii.gz                 # or __PET / _PET
├── finals_not_refined/<ID>.nii.gz  # source masks to refine (defines the case list)
└── last_batch/<ID>.nii.gz          # refined masks are saved here (created automatically)
```

- Only cases with a mask in `finals_not_refined/` **and** matching CT + PET files are loaded.
- If `last_batch/<ID>.nii.gz` exists it is loaded instead of the source mask.
- Edits to `T-stage` / `N-stage` are written back to `ehr.csv`.
- Cases are split evenly across annotators `1`–`4`; `ALL` shows every case.

## Quick start (command line)

```bash
pip install -r requirements.txt
python hecktor_viewer.py --data /path/to/data_folder
```

Options: `--annotator 1|2|3|4|ALL` (skip the selector), `--patient <ID>`, `--tstage-csv <path>`.

## Quick start (double-click launchers)

1. **One time:** install Python 3.9+ (tick "Add Python to PATH" on Windows).
2. **One time:** run `setup_environment.bat` (Windows) or `setup_environment_mac.command` (macOS; run `make_executable.command` first if needed).
3. **Every time:** run `run_hecktor.bat` / `run_hecktor_mac.command`. It asks for your data folder path, or pass it as the first argument, or set the `HECKTOR_DATA` environment variable.
4. Optional (Windows): `check_installation.bat` verifies the environment.

## 🏥 **Start Annotating (Every Time You Want to Use the Tool)**

1. **Double-click** on **`run_hecktor.bat`**
2. Wait a moment for the tool to load
3. Select your **Annotator ID** when prompted: `1`, `2`, `3`, `4`, or `ALL`
4. Click **"Start Annotation"**

## 🖱️ **Using the Annotation Tool**

### **Interface Overview:**

* **Left side** : Medical images (CT and PET scans)
* **Right side** : Raw EHR values, editable `T-stage`/`N-stage` fields, tool controls, and segmentation rules

### **Basic Workflow:**

1. **Start with label 1 / GTVp** - Review CT first, then PET support.
2. Remove air pockets, airway lumen, bone, teeth, vessels, normal fat, and PET spillover outside the CT tumor boundary.
3. **Then review label 2 / GTVn** - Keep nodes separate from GTVp and remove vessels, muscle, glands, bone, artifact, and isolated specks.
4. Use **Smart Interpolate** and **Clean Up** only after checking the key edited slices.
5. Click **Save Segmentation** when done.

### **T-stage Quick Reference**

* **T0** : No GTVp mask / no primary tumor mask visible
* **T1** : Tumor `<= 2 cm` in greatest dimension
* **T2** : Tumor `> 2 cm` and `<= 4 cm` in greatest dimension
* **T3** : Tumor `> 4 cm`, or extension to lingual surface of epiglottis
* **T4** : Advanced local invasion. Select `T4` for either T4a or T4b.

T4a includes invasion of the larynx, extrinsic tongue muscle, medial pterygoid, hard palate, or mandible. T4b includes invasion of lateral pterygoid muscle/plates, lateral nasopharynx, skull base, or carotid encasement. Mucosal extension to the lingual surface of the epiglottis from base of tongue/vallecula tumors does not count as larynx invasion.

### **Navigation:**

* **Mouse wheel** : Scroll through slices
* **Left/Right arrows** : Previous/Next patient
* **Zoom** : Ctrl + mouse wheel

## 💾 **Saving Your Work**

1. Click **"Save Segmentation"** button (right panel)
2. Your segmentation is saved to `<data folder>/last_batch/<ID>.nii.gz`
3. Edits to `T-stage` and `N-stage` are saved to `<data folder>/ehr.csv`
4. Use **"Next Patient"** to move to the next case

## 📊 **Track Your Progress**

* The progress bar shows how many patients you've completed
* Completed patients will show a ✓ checkmark

---

## 🆘 **If You Have Problems:**

### **"Python is not recognized" or similar error**

* Python needs to be installed

### **"Data folder does not exist" / no patients found**

* Check the path you passed to `--data`
* Check the folder matches the layout above (masks in `finals_not_refined/`, CT and PET next to them)

### **Tool won't start**

* Try right-clicking `run_hecktor.bat` and selecting "Run as administrator" (Windows)

### **Can't see images clearly**

* Adjust the contrast using the controls in the viewer
* Try toggling the PET overlay on/off

---

## 📋 **Annotation Guidelines Reminder:**

### **Label 1 - Primary Tumor (GTVp):**

* Include entire morphologic abnormality on CT
* Include hypermetabolic volume on PET
* Exclude nearby lymph nodes

### **Label 2 - Lymph Nodes (GTVn):**

* Criteria: SUV>2.5 OR diameter ≥1cm
* Include morphologic lymphadenopathy
* Must be separated from primary tumor
