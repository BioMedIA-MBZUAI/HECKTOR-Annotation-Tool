import os
import glob
import re
import csv
import warnings

import numpy as np
import napari
import nibabel as nib
import nibabel.processing as nproc
from PyQt5.QtWidgets import (QPushButton, QVBoxLayout, QWidget, QHBoxLayout, 
                            QComboBox, QLabel, QMessageBox, QSlider, QSpinBox,
                            QProgressBar, QDialog, QLineEdit, QDialogButtonBox,
                            QApplication, QScrollArea)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont
from scipy import ndimage
from skimage import morphology
from skimage.filters import gaussian
import argparse
import sys


class _NumpyWhereOutProxy:
    """Proxy NumPy in napari's triangulation module to silence its ruler warning."""

    def __init__(self, numpy_module):
        self._numpy_module = numpy_module
        self._hecktor_where_out_proxy = True

    def __getattr__(self, name):
        return getattr(self._numpy_module, name)

    def divide(self, *args, **kwargs):
        if "where" in kwargs and "out" not in kwargs:
            kwargs["out"] = None
        return self._numpy_module.divide(*args, **kwargs)


def _patch_napari_shape_triangulation_warning():
    """
    Avoid NumPy's "where used without out" warning when drawing ruler lines.

    The warning is emitted inside napari's pure-Python shapes triangulation
    fallback. Supplying out=None preserves napari's behavior and follows the
    warning's recommendation.
    """
    try:
        from napari.layers.shapes import _accelerated_triangulate_python as tri_py

        if not getattr(tri_py.np, "_hecktor_where_out_proxy", False):
            tri_py.np = _NumpyWhereOutProxy(tri_py.np)
    except Exception:
        warnings.filterwarnings(
            "ignore",
            message=r".*where.*without.*out.*",
            category=UserWarning,
        )


_patch_napari_shape_triangulation_warning()

SOURCE_MASKS_SUBDIR = "finals_not_refined"
PREPROCESSED_MASKS_SUBDIR = "finals_not_refined"
REFINED_MASKS_SUBDIR = "last_batch"
PRIMARY_TSTAGE_FILENAME = "primary_tumor_validation_tstage.csv"
EXCLUDED_SOURCE_MASK_PATIENT_IDS = set()


def read_image_nib(path: str):
    """
    Read a local NIfTI image using nibabel.

    Returns:
        data: 3D numpy array (z, y, x)
        spacing: tuple of (x_spacing, y_spacing, z_spacing)
        affine: 4x4 affine matrix
    """
    img = nib.load(path)
    img = nib.as_closest_canonical(img)
    data = img.get_fdata().astype(np.float32)
    # Nibabel zooms are (x, y, z)
    zooms = img.header.get_zooms()
    if len(zooms) >= 3:
        spacing = (float(zooms[0]), float(zooms[1]), float(zooms[2]))
    else:
        spacing = (1.0, 1.0, 1.0)
    affine = img.affine
    # Return data in (z, y, x) order
    if data.ndim == 3:
        data = np.transpose(data, (2, 1, 0))
    return data, spacing, affine


def exists_path(path: str) -> bool:
    return os.path.exists(path)


def list_relative_files(folder: str):
    """Return all file paths under folder, relative to it, using '/' separators."""
    files = set()
    for root, _, names in os.walk(folder):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), folder)
            files.add(rel.replace(os.sep, "/"))
    return files


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="HECKTOR Viewer")
    parser.add_argument(
        '--data',
        type=str,
        required=True,
        help="Local data folder (CT/PET files, ehr.csv, finals_not_refined/, last_batch/)"
    )
    parser.add_argument('--patient', type=str, help="Specific patient to load")
    parser.add_argument('--annotator', type=str, help="Annotator ID")
    parser.add_argument(
        '--tstage-csv',
        type=str,
        default=None,
        help="Optional primary tumor T-stage CSV path"
    )
    return parser.parse_args()

class AnnotatorLoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.annotator_id = None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("HECKTOR Annotator Login")
        self.setModal(True)
        # CHANGE 1: Made the dialog much larger to fit all text properly
        self.setFixedSize(800, 400)
        # Ensure dialog appears on top and is visible
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        # CHANGE 2: Added more spacing between elements
        layout.setSpacing(30)
        layout.setContentsMargins(50, 40, 50, 40)
        
        # Title
        title_label = QLabel("HECKTOR Segmentation Tool")
        title_font = QFont()
        title_font.setPointSize(18)  # Made much larger
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Add some vertical space after title
        layout.addSpacing(5)
        
        # Instructions
        instruction_label = QLabel("Please select your annotator ID:")
        instruction_label.setAlignment(Qt.AlignLeft)
        instruction_font = QFont()
        instruction_font.setPointSize(14)  # Made larger
        instruction_label.setFont(instruction_font)
        layout.addWidget(instruction_label)
        
        # Add spacing before input
        layout.addSpacing(5)
        
        # ID selection dropdown
        id_layout = QHBoxLayout()
        id_layout.setSpacing(5)
        
        id_label = QLabel("Annotator ID:")
        id_label_font = QFont()
        id_label_font.setPointSize(12)  # Made larger
        id_label.setFont(id_label_font)
        id_layout.addWidget(id_label)
        
        self.id_combo = QComboBox()
        self.id_combo.addItems(["1", "2", "3", "4", "ALL"])
        self.id_combo.setMinimumHeight(50)  # Made taller
        self.id_combo.setStyleSheet("""
            QComboBox {
                padding: 10px;
                font-size: 16px;
                border: 2px solid #ccc;
                border-radius: 5px;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox QAbstractItemView {
                font-size: 16px;
                padding: 5px;
            }
        """)
        id_layout.addWidget(self.id_combo)
        
        layout.addLayout(id_layout)
        
        # Add flexible space to push buttons to bottom
        # layout.addStretch()
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("""
            QDialogButtonBox QPushButton {
                min-width: 160px;
                min-height: 45px;
                font-size: 24px;
                font-weight: bold;
                padding: 12px 25px;
                margin: 10px;
                border-radius: 8px;
            }
        """)
        
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setText("Start Annotation")
        self.ok_button.setEnabled(True)  # Always enabled since dropdown has valid options
        
        cancel_button = button_box.button(QDialogButtonBox.Cancel)
        cancel_button.setText("Cancel")
        
        button_box.accepted.connect(self.accept_login)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
        # Focus on dropdown
        self.id_combo.setFocus()
    
    def accept_login(self):
        """Accept the login - get selected ID from dropdown"""
        # Get selected value from dropdown (already validated since it's from a fixed list)
        self.annotator_id = self.id_combo.currentText().strip().upper()
        self.accept()
    
    def get_annotator_id(self):
        """Get the entered annotator ID"""
        return self.annotator_id


class HECKTORViewer:
    # CT Windowing presets for different anatomical structures
    CT_WINDOWING_PRESETS = {
        "Auto": None,  # Will use auto-contrast
        "Soft Tissue": {"window": 350, "level": 40},
        "Bone": {"window": 2800, "level": 600},
        "Lung": {"window": 1500, "level": -600},
        "Brain": {"window": 80, "level": 40}
    }
    
    def __init__(self, data_folder, annotator_id, finals_folder=None, logo_path=None, tstage_csv_path=None):
        """
        Initialize the HECKTOR dataset viewer
        
        Parameters:
        -----------
        data_folder : str
            Path to the folder containing all scans
        annotator_id : str
            ID of the current annotator
        finals_folder : str, optional
            Path to save the edited masks
        logo_path : str, optional
            Path to logo image file
        tstage_csv_path : str, optional
            Path or URL to primary tumor T-stage validation CSV
        """
        self.data_folder = data_folder
        # Masks now live in the SAME folder as CT/PT (no separate "labels" subfolder)
        # in the data folder.
        # Keep a separate attribute for clarity, but point it at the data folder.
        self.labels_folder = data_folder
        self.source_masks_subdir = SOURCE_MASKS_SUBDIR
        self.preprocessed_masks_subdir = PREPROCESSED_MASKS_SUBDIR
        self.refined_masks_subdir = REFINED_MASKS_SUBDIR
        self.source_masks_folder = os.path.join(data_folder, self.source_masks_subdir)
        self.preprocessed_masks_folder = os.path.join(data_folder, self.preprocessed_masks_subdir)
        self.refined_masks_folder = os.path.join(data_folder, self.refined_masks_subdir)
        
        # Helper to extract base patient ID (removes _whole_body or _cropped suffix)
        # e.g., "CHUB-030_whole_body" -> "CHUB-030"
        def get_base_patient_id(patient_id):
            """Extract base patient ID by removing variant suffix"""
            if patient_id.endswith("_whole_body"):
                return patient_id[:-11]  # Remove "_whole_body"
            elif patient_id.endswith("_cropped"):
                return patient_id[:-8]  # Remove "_cropped"
            return patient_id
        self.get_base_patient_id = get_base_patient_id
        self.logo_path = logo_path
        
        # Validate annotator_id: must be 1-4 or "ALL"
        annotator_id_str = str(annotator_id).strip().upper()
        if annotator_id_str not in ["1", "2", "3", "4", "ALL"]:
            raise ValueError(
                f"Invalid annotator_id: {annotator_id}. "
                f"Must be 1, 2, 3, 4, or 'ALL' (case-insensitive)."
            )
        self.annotator_id = annotator_id_str
        self.current_patient_id = None
        self.ruler_layer = None
        self.ruler_active = False
        self._ruler_data_count_at_activation = 0

        self.ehr_file_path = os.path.join(self.data_folder, "ehr.csv")
        self.ehr_fieldnames = []
        self.ehr_rows = []
        self.ehr_patient_index = {}
        self.ehr_widgets = {}
        self.ehr_summary_widgets = {}
        self.ehr_status_label = None
        self.nstage_flag_label = None
        self.ehr_modified = False
        self.ehr_patient_field = "Patient #"
        self.ehr_patient_aliases = ["Patient #", "PatientID", "Patient ID", "patient_id"]
        self.ehr_old_t_stage_field = "T-stage"
        self.ehr_new_t_stage_field = "T-stage Final"
        self.ehr_old_n_stage_field = "N-stage"
        self.ehr_regenerated_n_stage_field = "N-stage_regenerated"
        self.ehr_new_n_stage_field = "N-stage Final"
        self.ehr_static_fields = [
            "tumor_laterality",
            "ln_count",
            "ln_total_volume_mm3",
            "ln_max_volume_mm3",
            "ln_max_diameter_3d_mm",
            "ln_side_relative_to_tumor",
            "ln_side_anatomic",
        ]
        self.ehr_treatment_options = [
            ("Chemotherapy", "Chemotherapy"),
            ("Surgery", "Surgery"),
            ("Radiation", "radiation"),
            ("Chemo Radiation", "Chemo Radiation"),
            ("Immunotherapy", "Immunotherapy")
        ]
        self.tstage_csv_path = None
        self.tstage_fieldnames = []
        self.tstage_rows = []
        self.tstage_patient_index = {}
        self.tstage_widgets = {}
        self.tstage_flag_label = None
        self.tstage_status_label = None
        self.tstage_patient_field = "PatientID"
        self.tstage_flag_field = "t_stage_match_flag"
        self.tstage_static_fields = [
            "t_stage_ehr",
            "t_stage_suggest",
            self.tstage_flag_field,
            "tumor_volume_mm3",
            "tumor_max_diameter_3d_mm",
            "tumor_max_diameter_axial_mm",
            "tumor_laterality",
        ]
        self._load_ehr_data()
        
        # Edited segmentations are saved to <data>/last_batch/<patient_id>.nii.gz
        self.finals_folder = finals_folder or self.refined_masks_folder
        
        # Get patient IDs (already filtered by annotator group inside _get_patients)
        self.patients = self._get_patients()
        self.current_patient_idx = -1  # No patient loaded initially
        
        # Track completed patients (by this annotator)
        self.completed_patients = self._get_completed_patients()
        
        # Initialize napari viewer with bottom controls always visible
        self.viewer = napari.Viewer(title=f"HECKTOR Segmentation Editor - Annotator: {self.annotator_id}")
        
        # Ensure bottom controls (slice slider) remain visible in fullscreen
        self._ensure_controls_visible()
        
        # Add custom UI widgets
        self._create_ui()
        
        # Load the first patient if available
        if self.patients:
            self.current_patient_idx = 0
            self.load_patient(self.patients[0])
        else:
            # Don't load any patient initially if none found
            self._update_patient_info()
            
        # Show instructions
        print("=" * 80)
        print(f"HECKTOR SEGMENTATION - ANNOTATOR: {self.annotator_id}")
        print("=" * 80)
        print("LABEL 1 - PRIMARY TUMOR (GTVp):")
        print("• Include entire morphologic anomaly (CT) + hypermetabolic volume (PET)")
        print("• EXCLUDE hypermetabolic activity outside physical tumor limits")
        print("• EXCLUDE nearby FDG-avid lymph nodes")
        print("• Check for tonsillectomy/extensive biopsy history")
        print("\nLABEL 2 - METASTATIC LYMPH NODES (GTVn):")
        print("• Criteria: SUV>2.5 OR diameter ≥1cm OR pathologically confirmed")
        print("• Include morphologic lymphadenopathy + hypermetabolic volume")
        print("• EXCLUDE activity on bony/muscular/vascular structures")
        print("• GTVp and GTVn must be SEPARATED")
        print("\nWORKFLOW:")
        print("1. Review CT morphology + PET uptake")
        print("2. Segment key slices → Smart Interpolate → Clean Up → Save")
        print(f"\nSaved files are written to {self.finals_folder} using the patient ID filename.")
        print("=" * 80)

    def _patient_id_from_ehr_row(self, row):
        """Return patient ID from accepted EHR patient ID column aliases."""
        for field in self.ehr_patient_aliases:
            value = (row.get(field) or "").strip()
            if value:
                return value
        return ""

    def _patient_id_from_tstage_row(self, row):
        """Return patient ID from the primary tumor T-stage CSV row."""
        value = (row.get(self.tstage_patient_field) or "").strip()
        if value:
            return value
        for field in self.ehr_patient_aliases:
            value = (row.get(field) or "").strip()
            if value:
                return value
        return ""

    def _resolve_tstage_csv_path(self, provided_path=None):
        """Resolve the primary tumor T-stage CSV from explicit path, sidecar, or data folder."""
        if provided_path:
            return provided_path

        script_dir = os.path.dirname(os.path.abspath(__file__))
        sidecar_path = os.path.join(script_dir, PRIMARY_TSTAGE_FILENAME)
        if os.path.exists(sidecar_path):
            return sidecar_path

        return os.path.join(self.data_folder, PRIMARY_TSTAGE_FILENAME)

    def _load_tstage_data(self):
        """Load primary tumor T-stage validation data into memory."""
        self.tstage_fieldnames = []
        self.tstage_rows = []
        self.tstage_patient_index = {}

        if not self.tstage_csv_path:
            print("Primary tumor T-stage CSV path is not configured.")
            return

        try:
            if not os.path.exists(self.tstage_csv_path):
                print(f"Primary tumor T-stage CSV not found at {self.tstage_csv_path}.")
                return
            csvfile = open(self.tstage_csv_path, newline='', encoding='utf-8-sig')

            try:
                reader = csv.DictReader(csvfile)
                raw_fieldnames = reader.fieldnames or []
                cleaned_fieldnames = []
                seen = set()
                for field in raw_fieldnames:
                    clean_field = field.strip().replace('\ufeff', '')
                    if clean_field and clean_field not in seen:
                        cleaned_fieldnames.append(clean_field)
                        seen.add(clean_field)

                self.tstage_fieldnames = cleaned_fieldnames

                for row in reader:
                    clean_row = {}
                    for key, value in row.items():
                        if key:
                            clean_key = key.strip().replace('\ufeff', '')
                            if clean_key in self.tstage_fieldnames:
                                clean_row[clean_key] = value

                    patient_id = self._patient_id_from_tstage_row(clean_row)
                    if not patient_id:
                        continue
                    clean_row[self.tstage_patient_field] = patient_id
                    self.tstage_rows.append(clean_row)
                    self.tstage_patient_index[patient_id] = clean_row

                    base_patient_id = self.get_base_patient_id(patient_id)
                    if base_patient_id != patient_id and base_patient_id not in self.tstage_patient_index:
                        self.tstage_patient_index[base_patient_id] = clean_row

                print(
                    f"Loaded {len(self.tstage_rows)} primary tumor T-stage entries "
                    f"from {self.tstage_csv_path}"
                )
            finally:
                csvfile.close()
        except Exception as exc:
            print(f"Failed to load primary tumor T-stage data: {exc}")
            import traceback
            traceback.print_exc()
            self.tstage_fieldnames = []
            self.tstage_rows = []
            self.tstage_patient_index = {}

    def _join_data(self, filename: str) -> str:
        return os.path.join(self.data_folder, filename)

    def _join_labels(self, filename: str) -> str:
        return os.path.join(self.labels_folder, filename)

    def _join_source_masks(self, filename: str) -> str:
        return os.path.join(self.source_masks_folder, filename)

    def _join_preprocessed_masks(self, filename: str) -> str:
        return os.path.join(self.preprocessed_masks_folder, filename)

    def _join_finals(self, filename: str) -> str:
        return os.path.join(self.finals_folder, filename)

    def _variant_suffix_for_patient(self, patient_id: str) -> str:
        if patient_id.endswith("_whole_body"):
            return "_whole_body"
        if patient_id.endswith("_cropped"):
            return "_cropped"
        return ""

    def _ct_candidate_names(self, patient_id: str):
        base_patient_id = self.get_base_patient_id(patient_id)
        variant_suffix = self._variant_suffix_for_patient(patient_id)
        if variant_suffix:
            return [
                f"{patient_id}/{patient_id}__CT.nii.gz",
                f"{patient_id}/{patient_id}__CT.mha",
                f"{patient_id}__CT.nii.gz",
                f"{patient_id}__CT.mha",
                f"{base_patient_id}_CT{variant_suffix}.nii.gz",
                f"{base_patient_id}_CT{variant_suffix}.mha",
                f"{base_patient_id}{variant_suffix}_CT.nii.gz",
                f"{base_patient_id}{variant_suffix}_CT.mha",
            ]

        candidates = [
            f"{patient_id}/{patient_id}__CT.nii.gz",
            f"{patient_id}/{patient_id}__CT.mha",
            f"{base_patient_id}/{base_patient_id}__CT.nii.gz",
            f"{base_patient_id}/{base_patient_id}__CT.mha",
            f"{patient_id}__CT.nii.gz",
            f"{patient_id}__CT.mha",
            f"{base_patient_id}__CT.nii.gz",
            f"{base_patient_id}__CT.mha",
            f"{base_patient_id}_CT.nii.gz",
            f"{base_patient_id}_CT.mha",
        ]
        candidates.extend([
            f"{base_patient_id}_CT_whole_body.nii.gz",
            f"{base_patient_id}_CT_whole_body.mha",
            f"{base_patient_id}_CT_cropped.nii.gz",
            f"{base_patient_id}_CT_cropped.mha",
        ])
        return candidates

    def _pt_candidate_names(self, patient_id: str):
        base_patient_id = self.get_base_patient_id(patient_id)
        variant_suffix = self._variant_suffix_for_patient(patient_id)
        if variant_suffix:
            return [
                f"{patient_id}/{patient_id}__PT.nii.gz",
                f"{patient_id}/{patient_id}__PT.mha",
                f"{patient_id}__PT.nii.gz",
                f"{patient_id}__PT.mha",
                f"{patient_id}/{patient_id}__PET.nii.gz",
                f"{patient_id}/{patient_id}__PET.mha",
                f"{patient_id}__PET.nii.gz",
                f"{patient_id}__PET.mha",
                f"{base_patient_id}_PT{variant_suffix}.nii.gz",
                f"{base_patient_id}_PT{variant_suffix}.mha",
                f"{base_patient_id}{variant_suffix}_PT.nii.gz",
                f"{base_patient_id}{variant_suffix}_PT.mha",
                f"{base_patient_id}_PET{variant_suffix}.nii.gz",
                f"{base_patient_id}_PET{variant_suffix}.mha",
                f"{base_patient_id}{variant_suffix}_PET.nii.gz",
                f"{base_patient_id}{variant_suffix}_PET.mha",
            ]

        candidates = [
            f"{patient_id}/{patient_id}__PT.nii.gz",
            f"{patient_id}/{patient_id}__PT.mha",
            f"{base_patient_id}/{base_patient_id}__PT.nii.gz",
            f"{base_patient_id}/{base_patient_id}__PT.mha",
            f"{patient_id}__PT.nii.gz",
            f"{patient_id}__PT.mha",
            f"{base_patient_id}__PT.nii.gz",
            f"{base_patient_id}__PT.mha",
            f"{patient_id}/{patient_id}__PET.nii.gz",
            f"{patient_id}/{patient_id}__PET.mha",
            f"{base_patient_id}/{base_patient_id}__PET.nii.gz",
            f"{base_patient_id}/{base_patient_id}__PET.mha",
            f"{base_patient_id}_PET.nii.gz",
            f"{base_patient_id}_PET.mha",
        ]
        candidates.extend([
            f"{base_patient_id}_PET_whole_body.nii.gz",
            f"{base_patient_id}_PET_whole_body.mha",
            f"{base_patient_id}_PET_cropped.nii.gz",
            f"{base_patient_id}_PET_cropped.mha",
        ])
        return candidates

    def _candidate_image_pairs(self, patient_id: str):
        """Return CT/PT candidate groups, keeping cropped/whole_body variants paired."""
        base_patient_id = self.get_base_patient_id(patient_id)
        variant_suffix = self._variant_suffix_for_patient(patient_id)
        if variant_suffix:
            return [
                (
                    variant_suffix.lstrip("_"),
                    self._ct_candidate_names(patient_id),
                    self._pt_candidate_names(patient_id),
                )
            ]

        return [
            (
                "direct",
                [
                    f"{patient_id}/{patient_id}__CT.nii.gz",
                    f"{base_patient_id}/{base_patient_id}__CT.nii.gz",
                    f"{patient_id}__CT.nii.gz",
                    f"{base_patient_id}__CT.nii.gz",
                    f"{base_patient_id}_CT.nii.gz",
                    f"{base_patient_id}_CT.mha",
                ],
                [
                    f"{patient_id}/{patient_id}__PT.nii.gz",
                    f"{base_patient_id}/{base_patient_id}__PT.nii.gz",
                    f"{patient_id}__PT.nii.gz",
                    f"{base_patient_id}__PT.nii.gz",
                    f"{patient_id}/{patient_id}__PET.nii.gz",
                    f"{base_patient_id}/{base_patient_id}__PET.nii.gz",
                    f"{base_patient_id}_PET.nii.gz",
                    f"{base_patient_id}_PET.mha",
                ],
            ),
            (
                "cropped",
                [
                    f"{base_patient_id}_CT_cropped.nii.gz",
                    f"{base_patient_id}_CT_cropped.mha",
                ],
                [
                    f"{base_patient_id}_PET_cropped.nii.gz",
                    f"{base_patient_id}_PET_cropped.mha",
                    f"{base_patient_id}_cropped_PET.nii.gz",
                    f"{base_patient_id}_cropped_PET.mha",
                ],
            ),
            (
                "whole_body",
                [
                    f"{base_patient_id}_CT_whole_body.nii.gz",
                    f"{base_patient_id}_CT_whole_body.mha",
                ],
                [
                    f"{base_patient_id}_PET_whole_body.nii.gz",
                    f"{base_patient_id}_PET_whole_body.mha",
                    f"{base_patient_id}_whole_body_PET.nii.gz",
                    f"{base_patient_id}_whole_body_PET.mha",
                ],
            ),
        ]

    def _first_existing_data_path(self, filenames):
        """Return the first existing data path and all resolved paths tried."""
        tried_paths = []
        for filename in filenames:
            path = self._join_data(filename)
            tried_paths.append(path)
            if exists_path(path):
                return path, tried_paths
        return tried_paths[0], tried_paths

    def _score_mask_against_ct_grid(self, mask_file: str, ct_file: str):
        """Score how well a mask lands on a CT grid after nearest-neighbor resampling."""
        mask_array, _, mask_affine = read_image_nib(mask_file)
        ct_array, _, ct_affine = read_image_nib(ct_file)
        if mask_affine is None or ct_affine is None:
            return {
                "nonzero": int(np.count_nonzero(mask_array)),
                "density": 0.0,
                "exact": mask_array.shape == ct_array.shape,
                "ct_voxels": int(np.prod(ct_array.shape)),
            }

        ct_shape_xyz = (ct_array.shape[2], ct_array.shape[1], ct_array.shape[0])
        mask_shape_xyz = (mask_array.shape[2], mask_array.shape[1], mask_array.shape[0])
        exact = mask_shape_xyz == ct_shape_xyz and np.allclose(mask_affine, ct_affine, rtol=0, atol=1e-3)
        if exact:
            nonzero = int(np.count_nonzero(mask_array))
        else:
            mask_img = nib.Nifti1Image(np.transpose(mask_array, (2, 1, 0)).astype(np.float32), mask_affine)
            resampled_img = nproc.resample_from_to(mask_img, (ct_shape_xyz, ct_affine), order=0)
            nonzero = int(np.count_nonzero(np.rint(resampled_img.get_fdata())))

        ct_voxels = int(np.prod(ct_shape_xyz))
        return {
            "nonzero": nonzero,
            "density": nonzero / ct_voxels if ct_voxels else 0.0,
            "exact": exact,
            "ct_voxels": ct_voxels,
        }

    def _select_ct_pt_files(self, patient_id: str, mask_reference_file: str | None = None):
        """Select a paired CT/PT variant, using mask geometry for unsuffixed source masks."""
        tried_ct_paths = []
        tried_pt_paths = []
        available_pairs = []

        for variant_name, ct_candidates, pt_candidates in self._candidate_image_pairs(patient_id):
            ct_file, ct_tried = self._first_existing_data_path(ct_candidates)
            pt_file, pt_tried = self._first_existing_data_path(pt_candidates)
            tried_ct_paths.extend(ct_tried)
            tried_pt_paths.extend(pt_tried)
            if exists_path(ct_file) and exists_path(pt_file):
                available_pairs.append((variant_name, ct_file, pt_file))

        if not available_pairs:
            return (
                tried_ct_paths[0] if tried_ct_paths else self._join_data(f"{patient_id}_CT.nii.gz"),
                tried_ct_paths,
                tried_pt_paths[0] if tried_pt_paths else self._join_data(f"{patient_id}_PET.nii.gz"),
                tried_pt_paths,
            )

        variant_suffix = self._variant_suffix_for_patient(patient_id)
        if variant_suffix or not mask_reference_file or not exists_path(mask_reference_file) or len(available_pairs) == 1:
            variant_name, ct_file, pt_file = available_pairs[0]
            print(f"Selected {variant_name} CT/PT pair for {patient_id}")
            return ct_file, tried_ct_paths, pt_file, tried_pt_paths

        scored_pairs = []
        for variant_name, ct_file, pt_file in available_pairs:
            try:
                score = self._score_mask_against_ct_grid(mask_reference_file, ct_file)
                scored_pairs.append((variant_name, ct_file, pt_file, score))
                print(
                    f"Candidate {variant_name} for {patient_id}: "
                    f"mask_on_ct_nonzero={score['nonzero']}, "
                    f"density={score['density']:.8f}, exact={score['exact']}"
                )
            except Exception as exc:
                print(f"Failed to score {variant_name} CT candidate for {patient_id}: {exc}")

        if scored_pairs:
            scored_pairs.sort(
                key=lambda item: (
                    bool(item[3]["exact"]),
                    item[3]["density"],
                    item[3]["nonzero"],
                    -item[3]["ct_voxels"],
                ),
                reverse=True,
            )
            variant_name, ct_file, pt_file, score = scored_pairs[0]
            if score["nonzero"] > 0:
                print(f"Selected {variant_name} CT/PT pair for {patient_id} based on mask geometry")
                return ct_file, tried_ct_paths, pt_file, tried_pt_paths

        variant_name, ct_file, pt_file = available_pairs[0]
        print(
            f"Warning: no CT candidate had non-empty mask overlap for {patient_id}; "
            f"falling back to {variant_name}."
        )
        return ct_file, tried_ct_paths, pt_file, tried_pt_paths

    def _to_display_orientation(self, array):
        """Flip the image vertically for the napari axial display."""
        return np.flip(array, axis=1)

    def _from_display_orientation(self, array):
        """Invert the display orientation before saving back to NIfTI."""
        return np.flip(array, axis=1)

    def _resample_mask_to_ct_grid(self, mask_array, mask_affine, ct_array, patient_id, mask_file_used):
        """Resample a label mask to the selected CT grid when its NIfTI geometry differs."""
        if mask_array is None:
            return mask_array

        if not hasattr(self, "ct_affine") or self.ct_affine is None or mask_affine is None:
            if mask_array.shape != ct_array.shape:
                print(
                    f"Warning: mask geometry unavailable for {patient_id}; "
                    f"mask shape {mask_array.shape} differs from CT shape {ct_array.shape}."
                )
            return mask_array

        ct_shape_xyz = (ct_array.shape[2], ct_array.shape[1], ct_array.shape[0])
        mask_shape_xyz = (mask_array.shape[2], mask_array.shape[1], mask_array.shape[0])
        same_shape = mask_shape_xyz == ct_shape_xyz
        same_affine = np.allclose(mask_affine, self.ct_affine, rtol=0, atol=1e-3)
        if same_shape and same_affine:
            return mask_array

        print(
            f"Resampling mask to CT grid for {patient_id}: "
            f"mask shape xyz={mask_shape_xyz}, CT shape xyz={ct_shape_xyz}, "
            f"source={mask_file_used}"
        )

        try:
            mask_img = nib.Nifti1Image(
                np.transpose(mask_array, (2, 1, 0)).astype(np.float32),
                mask_affine,
            )
            resampled_img = nproc.resample_from_to(
                mask_img,
                (ct_shape_xyz, self.ct_affine),
                order=0,
            )
            resampled = np.transpose(resampled_img.get_fdata(), (2, 1, 0))
            resampled = np.rint(resampled).astype(mask_array.dtype, copy=False)
            if np.count_nonzero(mask_array) and not np.count_nonzero(resampled):
                print(
                    f"Warning: resampling produced an empty mask for {patient_id}. "
                    "The source mask may not overlap the selected CT volume."
                )
            return resampled
        except Exception as exc:
            print(f"Warning: failed to resample mask for {patient_id}: {exc}")
            return mask_array

    def _ensure_controls_visible(self):
        """Ensure napari's built-in controls (including slice slider) remain visible in fullscreen"""
        # Access the Qt window
        qt_window = self.viewer.window._qt_window
        
        # Force the dims widget (which contains the slice slider) to always be visible
        dims_widget = self.viewer.window._qt_viewer.dims
        dims_widget.setVisible(True)
        
        # Set minimum height for the main window to ensure bottom controls don't get cut off
        qt_window.setMinimumHeight(600)
        
        # Ensure the status bar is visible (contains slice info)
        if hasattr(qt_window, 'statusBar'):
            qt_window.statusBar().setVisible(True)
        
        # Force layout update
        qt_window.adjustSize()
        
        print("Napari controls visibility ensured for fullscreen mode")
    
    def _load_ehr_data(self):
        """Load EHR data from CSV into memory"""
        self.ehr_fieldnames = []
        self.ehr_rows = []
        self.ehr_patient_index = {}
        
        if not os.path.exists(self.ehr_file_path):
            print(f"EHR file not found at {self.ehr_file_path}. EHR display will be empty.")
            return
        seeded_new_n_stage = False
        try:
            with open(self.ehr_file_path, newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                raw_fieldnames = reader.fieldnames or []
                
                # Clean field names (remove BOM, extra spaces, duplicates)
                cleaned_fieldnames = []
                seen = set()
                for field in raw_fieldnames:
                    clean_field = field.strip().replace('\ufeff', '')
                    if clean_field and clean_field not in seen:
                        cleaned_fieldnames.append(clean_field)
                        seen.add(clean_field)
                
                self.ehr_fieldnames = cleaned_fieldnames
                if self.ehr_patient_field not in self.ehr_fieldnames:
                    self.ehr_fieldnames.insert(0, self.ehr_patient_field)
                
                for row in reader:
                    # Clean row keys to match cleaned field names
                    clean_row = {}
                    for key, value in row.items():
                        if key:
                            clean_key = key.strip().replace('\ufeff', '')
                            if clean_key in self.ehr_fieldnames:
                                clean_row[clean_key] = value
                    
                    patient_id = self._patient_id_from_ehr_row(clean_row)
                    clean_row[self.ehr_patient_field] = patient_id
                    self.ehr_rows.append(clean_row)
                    if patient_id:
                        # Index by full patient ID
                        self.ehr_patient_index[patient_id] = clean_row
                        # Also index by base patient ID (without variant suffix)
                        # This allows variants to share the same EHR entry
                        base_patient_id = self.get_base_patient_id(patient_id)
                        if base_patient_id != patient_id:
                            # Only create base entry if it doesn't exist yet
                            # This way, if there are multiple variants, the first one loaded wins
                            if base_patient_id not in self.ehr_patient_index:
                                self.ehr_patient_index[base_patient_id] = clean_row
                seeded_new_n_stage = self._ensure_ehr_required_fields()
                print(f"Loaded {len(self.ehr_rows)} EHR entries with fields: {self.ehr_fieldnames}")
        except Exception as exc:
            print(f"Failed to load EHR data: {exc}")
            import traceback
            traceback.print_exc()
            self.ehr_fieldnames = []
            self.ehr_rows = []
            self.ehr_patient_index = {}
        self.ehr_modified = seeded_new_n_stage

    def _ensure_ehr_required_fields(self):
        """Ensure the editable raw EHR stage fields exist without adding review columns."""
        required_fields = [
            self.ehr_patient_field,
            self.ehr_old_t_stage_field,
            self.ehr_old_n_stage_field,
        ]
        added_required_fields = False
        for field in required_fields:
            if field not in self.ehr_fieldnames:
                self.ehr_fieldnames.append(field)
                added_required_fields = True

        for row in self.ehr_rows:
            for field in required_fields:
                if field not in row:
                    row[field] = ""
            patient_id = self._patient_id_from_ehr_row(row)
            if patient_id and row.get(self.ehr_patient_field) != patient_id:
                row[self.ehr_patient_field] = patient_id
                added_required_fields = True
        return added_required_fields
    
    def _write_ehr_csv(self, force_save=False):
        """Persist current EHR data to the local CSV if modified"""
        if not self.ehr_fieldnames:
            return
        
        # If not forcing save and no changes, just mark as modified
        if not force_save:
            self.ehr_modified = True
            return
        
        # Only save if there were actual changes
        if not self.ehr_modified:
            return
        
        try:
            with open(self.ehr_file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.ehr_fieldnames)
                writer.writeheader()
                writer.writerows(self.ehr_rows)
            self.ehr_modified = False
            print(f"✓ Saved updated EHR data to {self.ehr_file_path}")
        except Exception as e:
            print(f"✗ Failed to save EHR data: {e}")
            import traceback
            traceback.print_exc()
    
    def _ensure_patient_ehr_entry(self, patient_id):
        """Ensure there is an EHR entry for the given patient"""
        if not patient_id:
            return None

        base_patient_id = self.get_base_patient_id(patient_id)
        
        # Single lookup: Try exact patient ID first (for variant-specific entries)
        # If not found, use base patient ID (variants share same EHR entry)
        lookup_id = patient_id if patient_id in self.ehr_patient_index else base_patient_id
        
        if lookup_id in self.ehr_patient_index:
            entry = self.ehr_patient_index[lookup_id]
            entry[self.ehr_patient_field] = lookup_id
            return entry
        
        if not self.ehr_fieldnames:
            return None
        
        new_row = {field: "" for field in self.ehr_fieldnames}
        new_row[self.ehr_patient_field] = base_patient_id
        self.ehr_rows.append(new_row)
        self.ehr_patient_index[base_patient_id] = new_row
        self._write_ehr_csv()
        return new_row
    
    def _normalize_ehr_value_for_display(self, field, value):
        if value is None:
            return ""
        clean = str(value).strip()
        if not clean:
            return ""
        upper_clean = clean.upper()
        if upper_clean == "N/A":
            return "Unknown"
        if field == "Treatment":
            for display_text, stored_value in self.ehr_treatment_options:
                if clean.lower() == stored_value.lower():
                    return display_text
                if clean.lower() == display_text.lower():
                    return display_text
        if field == "HPV status":
            if clean == "+":
                return "Positive"
            if clean == "-":
                return "Negative"
            if upper_clean in {"UNKNOWN", "N/A"}:
                return "Unknown"
        if field in {"Tobacco Consumption", "Alcohol Consumption", "Surgery"}:
            if upper_clean in {"0", "NO"}:
                return "No"
            if upper_clean in {"1", "YES"}:
                return "Yes"
            if upper_clean in {"UNKNOWN", "N/A"}:
                return "Unknown"
        if field == "Sex":
            if upper_clean == "F":
                return "Female"
            if upper_clean == "M":
                return "Male"
        return clean
    
    def _normalize_ehr_value_for_storage(self, field, value):
        if value is None:
            return ""
        clean = str(value).strip()
        if not clean:
            return ""
        lower_clean = clean.lower()
        if lower_clean == "unknown":
            return "N/A"
        if field == "Sex":
            if lower_clean in {"female", "f"}:
                return "F"
            if lower_clean in {"male", "m", "make"}:
                return "M"
        if field == "Treatment":
            for display_text, stored_value in self.ehr_treatment_options:
                if lower_clean == display_text.lower():
                    return stored_value
                if lower_clean == stored_value.lower():
                    return stored_value
        if field == "HPV status":
            if lower_clean in {"positive", "+"}:
                return "+"
            if lower_clean in {"negative", "-"}:
                return "-"
            if lower_clean in {"unknown", "n/a"}:
                return "N/A"
        if field in {"Tobacco Consumption", "Alcohol Consumption", "Surgery"}:
            if lower_clean in {"no", "0"}:
                return "0"
            if lower_clean in {"yes", "1"}:
                return "1"
            if lower_clean in {"unknown", "n/a"}:
                return "N/A"
        return clean

    def _format_ehr_field_label(self, field):
        """Convert raw EHR column names into cleaner UI labels."""
        custom_labels = {
            self.ehr_new_t_stage_field: "T-stage (Final)",
            self.ehr_old_n_stage_field: "N-stage (Old)",
            self.ehr_regenerated_n_stage_field: "N-stage (Regenerated)",
            self.ehr_new_n_stage_field: "N-stage (New)",
            "T-stage": "T-stage",
            "M-stage": "M-stage",
            "PatientID": "Patient ID",
            "t_stage_ehr": "T-stage (EHR)",
            "t_stage_suggest": "T-stage Suggestion",
            "t_stage_match_flag": "T-stage Review Flag",
            "tumor_volume_mm3": "Tumor Volume (mm3)",
            "tumor_max_diameter_3d_mm": "Tumor Max Diameter 3D (mm)",
            "tumor_max_diameter_axial_mm": "Tumor Max Diameter Axial (mm)",
            "tumor_laterality": "Tumor Laterality",
        }
        if field in custom_labels:
            return custom_labels[field]

        cleaned = str(field or "").strip().replace("_", " ")
        if not cleaned:
            return ""
        token_overrides = {
            "mm3": "mm3",
            "mm": "mm",
            "3d": "3D",
        }
        formatted_parts = []
        for part in cleaned.split():
            lowered = part.lower()
            if lowered in token_overrides:
                formatted_parts.append(token_overrides[lowered])
            else:
                formatted_parts.append(part.capitalize())
        return " ".join(formatted_parts)

    def _t_stage_options(self):
        return [
            ("T0 - no GTVp mask", "T0"),
            ("T1 - <= 2 cm", "T1"),
            ("T2 - > 2 cm and <= 4 cm", "T2"),
            ("T3 - > 4 cm or lingual epiglottis", "T3"),
            ("T4 - advanced local invasion", "T4"),
        ]

    def _normalize_t_stage_choice(self, value):
        clean = str(value or "").strip().upper().replace(" ", "")
        if not clean:
            return ""
        if clean in {"0", "T0"}:
            return "T0"
        if clean in {"1", "1A", "1B", "T1", "T1A", "T1B"}:
            return "T1"
        if clean in {"2", "2A", "2B", "2C", "T2", "T2A", "T2B", "T2C"}:
            return "T2"
        if clean in {"3", "3A", "3B", "T3", "T3A", "T3B"}:
            return "T3"
        if clean.startswith("4") or clean.startswith("T4"):
            return "T4"
        return clean
    
    def _create_labeled_row(self, layout, label_text, value_widget, label_width=230):
        """Create a compact two-column row in the right panel."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        label = QLabel(label_text)
        label.setFixedWidth(label_width)
        row_layout.addWidget(label)

        row_layout.addWidget(value_widget, stretch=1)
        layout.addWidget(row_widget)

    def _create_ehr_summary_section(self, layout):
        """Create raw EHR fields with only T-stage and N-stage editable."""
        layout.addWidget(QLabel("<b>Patient EHR:</b>"))

        if not self.ehr_fieldnames:
            missing_label = QLabel("No EHR data available.")
            missing_label.setStyleSheet(
                "QLabel { background-color: #ffebee; color: #c62828; padding: 4px; border-radius: 4px; }"
            )
            layout.addWidget(missing_label)
            return

        self.ehr_summary_widgets = {}
        static_style = (
            "background-color: #f5f5f5; "
            "color: #263238; "
            "padding: 4px; "
            "border: 1px solid #d0d0d0; "
            "border-radius: 4px;"
        )
        editable_style = (
            "QLineEdit { "
            "background-color: #fff8e1; "
            "color: #263238; "
            "padding: 4px; "
            "border: 1px solid #ffb74d; "
            "border-radius: 4px; "
            "}"
        )
        editable_combo_style = (
            "QComboBox { "
            "background-color: #fff8e1; "
            "color: #263238; "
            "padding: 4px; "
            "border: 1px solid #ffb74d; "
            "border-radius: 4px; "
            "}"
        )
        editable_fields = {self.ehr_old_t_stage_field, self.ehr_old_n_stage_field}

        for field in self.ehr_fieldnames:
            if field == self.ehr_old_t_stage_field:
                value_widget = QComboBox()
                for display_text, stored_value in self._t_stage_options():
                    value_widget.addItem(display_text, stored_value)
                value_widget.setStyleSheet(editable_combo_style)
                value_widget.currentIndexChanged.connect(
                    lambda _index, f=field: self._on_ehr_value_changed(f)
                )
            elif field in editable_fields:
                value_widget = QLineEdit()
                value_widget.setStyleSheet(editable_style)
                value_widget.editingFinished.connect(
                    lambda f=field: self._on_ehr_value_changed(f)
                )
            else:
                value_widget = QLabel("")
                value_widget.setStyleSheet(static_style)
                value_widget.setWordWrap(True)

            self.ehr_summary_widgets[field] = value_widget
            self.ehr_widgets[field] = value_widget
            self._create_labeled_row(layout, f"{field}:", value_widget)

        self.ehr_status_label = QLabel("")
        self.ehr_status_label.setStyleSheet(
            "QLabel { color: #2e7d32; font-size: 10px; padding: 2px; }"
        )
        layout.addWidget(self.ehr_status_label)

    def _create_stage_tabs(self, layout):
        """Staging review tabs are intentionally disabled in this workflow."""
        return

    def _create_tstage_section(self, layout):
        """Create UI section for primary tumor T-stage validation data."""
        static_style = (
            "background-color: #eef7fb; "
            "color: #263238; "
            "padding: 4px; "
            "border: 1px solid #90caf9; "
            "border-radius: 4px;"
        )
        editable_style = (
            "QLineEdit { "
            "background-color: #fff8e1; "
            "color: #3e2723; "
            "padding: 4px; "
            "border: 1px solid #ffb74d; "
            "border-radius: 4px; "
            "}"
        )

        header = QLabel("<b>GTVp Primary Tumor:</b>")
        layout.addWidget(header)

        self.tstage_flag_label = QLabel("T-stage review: --")
        self.tstage_flag_label.setWordWrap(True)
        self.tstage_flag_label.setStyleSheet(
            "QLabel { background-color: #eeeeee; color: #424242; padding: 6px; "
            "border: 1px solid #bdbdbd; border-radius: 4px; font-weight: bold; }"
        )
        layout.addWidget(self.tstage_flag_label)

        if not self.tstage_fieldnames:
            missing_label = QLabel("No primary tumor T-stage CSV data available.")
            missing_label.setWordWrap(True)
            missing_label.setStyleSheet(
                "QLabel { background-color: #ffebee; color: #c62828; padding: 4px; border-radius: 4px; }"
            )
            layout.addWidget(missing_label)
        else:
            static_fields_in_view = [
                field for field in self.tstage_static_fields if field in self.tstage_fieldnames
            ]

            for field in static_fields_in_view:
                static_label = QLabel("")
                static_label.setStyleSheet(static_style)
                static_label.setWordWrap(True)
                self.tstage_widgets[field] = static_label
                self._create_labeled_row(
                    layout,
                    f"{self._format_ehr_field_label(field)}:",
                    static_label,
                )

        if self.ehr_fieldnames:
            editable_header = QLabel("<b>Editable Final Field:</b>")
            layout.addWidget(editable_header)

            input_widget = QLineEdit()
            input_widget.setStyleSheet(editable_style)
            input_widget.editingFinished.connect(
                lambda f=self.ehr_new_t_stage_field: self._on_ehr_value_changed(f)
            )
            self.ehr_widgets[self.ehr_new_t_stage_field] = input_widget
            self._create_labeled_row(
                layout,
                f"{self._format_ehr_field_label(self.ehr_new_t_stage_field)}:",
                input_widget,
            )

        self.tstage_status_label = QLabel("")
        self.tstage_status_label.setStyleSheet(
            "QLabel { color: #1565c0; font-size: 10px; padding: 2px; }"
        )
        layout.addWidget(self.tstage_status_label)

    def _create_gtvn_section(self, layout):
        """Create UI section for nodal GTVn/N-stage EHR data."""
        header = QLabel("<b>GTVn Lymph Nodes:</b>")
        layout.addWidget(header)

        if not self.ehr_fieldnames:
            missing_label = QLabel("No EHR data available.")
            missing_label.setStyleSheet(
                "QLabel { background-color: #ffebee; color: #c62828; padding: 4px; border-radius: 4px; }"
            )
            layout.addWidget(missing_label)
            return

        self.nstage_flag_label = QLabel("N-stage review: --")
        self.nstage_flag_label.setWordWrap(True)
        self.nstage_flag_label.setStyleSheet(
            "QLabel { background-color: #eeeeee; color: #424242; padding: 6px; "
            "border: 1px solid #bdbdbd; border-radius: 4px; font-weight: bold; }"
        )
        layout.addWidget(self.nstage_flag_label)

        static_style = (
            "background-color: #f0f4c3; "
            "color: #37474f; "
            "padding: 4px; "
            "border: 1px solid #cddc39; "
            "border-radius: 4px;"
        )
        editable_style = (
            "QLineEdit { "
            "background-color: #fff8e1; "
            "color: #3e2723; "
            "padding: 4px; "
            "border: 1px solid #ffb74d; "
            "border-radius: 4px; "
            "}"
        )

        static_fields_in_view = [
            self.ehr_old_n_stage_field,
            "ln_count",
            "ln_total_volume_mm3",
            "ln_max_volume_mm3",
            "ln_max_diameter_3d_mm",
            "ln_side_relative_to_tumor",
            "ln_side_anatomic",
        ]
        static_fields_in_view = [field for field in static_fields_in_view if field in self.ehr_fieldnames]

        for field in static_fields_in_view:
            static_label = QLabel("")
            static_label.setStyleSheet(static_style)
            static_label.setWordWrap(True)
            self.ehr_widgets[field] = static_label
            self._create_labeled_row(
                layout,
                f"{self._format_ehr_field_label(field)}:",
                static_label,
            )

        editable_header = QLabel("<b>Editable Final Field:</b>")
        layout.addWidget(editable_header)

        input_widget = QLineEdit()
        input_widget.setStyleSheet(editable_style)
        input_widget.editingFinished.connect(
            lambda f=self.ehr_new_n_stage_field: self._on_ehr_value_changed(f)
        )
        self.ehr_widgets[self.ehr_new_n_stage_field] = input_widget
        self._create_labeled_row(
            layout,
            f"{self._format_ehr_field_label(self.ehr_new_n_stage_field)}:",
            input_widget,
        )

        self.ehr_status_label = QLabel("")
        self.ehr_status_label.setStyleSheet(
            "QLabel { color: #2e7d32; font-size: 10px; padding: 2px; }"
        )
        layout.addWidget(self.ehr_status_label)

    def _tstage_entry_for_patient(self, patient_id):
        """Return the T-stage CSV row for a patient or its base variant ID."""
        if not patient_id:
            return None
        if patient_id in self.tstage_patient_index:
            return self.tstage_patient_index[patient_id]
        base_patient_id = self.get_base_patient_id(patient_id)
        return self.tstage_patient_index.get(base_patient_id)

    def _format_tstage_value_for_display(self, field, value):
        """Format primary tumor T-stage CSV values for the right-panel tab."""
        if value is None:
            return ""
        clean = str(value).strip()
        if not clean:
            return ""

        if field == "tumor_volume_mm3":
            try:
                return f"{float(clean):,.0f} mm3"
            except ValueError:
                return clean

        if field in {"tumor_max_diameter_3d_mm", "tumor_max_diameter_axial_mm"}:
            try:
                return f"{float(clean):.1f} mm"
            except ValueError:
                return clean

        if field == self.tstage_flag_field:
            return clean.replace("_", " ").capitalize()

        return clean

    def _set_tstage_flag_display(self, entry):
        """Update the prominent needs-revision flag on the GTVp tab."""
        if self.tstage_flag_label is None:
            return

        if entry is None:
            self.tstage_flag_label.setText("T-stage review: no CSV row")
            self.tstage_flag_label.setStyleSheet(
                "QLabel { background-color: #eeeeee; color: #424242; padding: 6px; "
                "border: 1px solid #bdbdbd; border-radius: 4px; font-weight: bold; }"
            )
            return

        flag = (entry.get(self.tstage_flag_field) or "").strip().lower()
        if flag == "needs_revision":
            self.tstage_flag_label.setText("T-stage review: NEEDS REVISION")
            self.tstage_flag_label.setStyleSheet(
                "QLabel { background-color: #ffebee; color: #b71c1c; padding: 6px; "
                "border: 1px solid #ef5350; border-radius: 4px; font-weight: bold; }"
            )
        elif flag == "correct_match":
            self.tstage_flag_label.setText("T-stage review: correct match")
            self.tstage_flag_label.setStyleSheet(
                "QLabel { background-color: #e8f5e9; color: #1b5e20; padding: 6px; "
                "border: 1px solid #66bb6a; border-radius: 4px; font-weight: bold; }"
            )
        else:
            display_flag = self._format_tstage_value_for_display(self.tstage_flag_field, flag)
            self.tstage_flag_label.setText(f"T-stage review: {display_flag or 'unknown'}")
            self.tstage_flag_label.setStyleSheet(
                "QLabel { background-color: #fff8e1; color: #5d4037; padding: 6px; "
                "border: 1px solid #ffb74d; border-radius: 4px; font-weight: bold; }"
            )

    def _update_tstage_display(self, patient_id):
        """Update primary tumor T-stage tab widgets for the current patient."""
        if self.tstage_flag_label is None and not self.tstage_widgets:
            return

        if not patient_id:
            if self.tstage_flag_label is not None:
                self.tstage_flag_label.setText("T-stage review: --")
                self.tstage_flag_label.setStyleSheet(
                    "QLabel { background-color: #eeeeee; color: #424242; padding: 6px; "
                    "border: 1px solid #bdbdbd; border-radius: 4px; font-weight: bold; }"
                )
            for widget in self.tstage_widgets.values():
                widget.setText("")
            if self.tstage_status_label is not None:
                self.tstage_status_label.setText("")
            return

        entry = self._tstage_entry_for_patient(patient_id)
        self._set_tstage_flag_display(entry)

        if entry is None:
            for widget in self.tstage_widgets.values():
                widget.setText("N/A")
            if self.tstage_status_label is not None:
                self.tstage_status_label.setText(f"No T-stage CSV row for patient {patient_id}")
            return

        for field, widget in self.tstage_widgets.items():
            display_value = self._format_tstage_value_for_display(field, entry.get(field, ""))
            widget.setText(display_value or "N/A")

        if self.tstage_status_label is not None:
            source_patient_id = entry.get(self.tstage_patient_field, patient_id)
            self.tstage_status_label.setText(f"Loaded T-stage CSV row for patient {source_patient_id}")

    def _normalize_stage_for_compare(self, value):
        """Normalize stage text before old/new comparison."""
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    def _set_nstage_flag_display(self, entry):
        """Update the GTVn review flag from old versus final N-stage values."""
        if self.nstage_flag_label is None:
            return

        if entry is None:
            self.nstage_flag_label.setText("N-stage review: no EHR row")
            self.nstage_flag_label.setStyleSheet(
                "QLabel { background-color: #eeeeee; color: #424242; padding: 6px; "
                "border: 1px solid #bdbdbd; border-radius: 4px; font-weight: bold; }"
            )
            return

        old_n_stage = (entry.get(self.ehr_old_n_stage_field) or "").strip()
        new_n_stage = (entry.get(self.ehr_new_n_stage_field) or "").strip()
        normalized_old = self._normalize_stage_for_compare(old_n_stage)
        normalized_new = self._normalize_stage_for_compare(new_n_stage)

        if not normalized_old or not normalized_new:
            self.nstage_flag_label.setText("N-stage review: incomplete old/new stage")
            self.nstage_flag_label.setStyleSheet(
                "QLabel { background-color: #fff8e1; color: #5d4037; padding: 6px; "
                "border: 1px solid #ffb74d; border-radius: 4px; font-weight: bold; }"
            )
        elif normalized_old != normalized_new:
            self.nstage_flag_label.setText("N-stage review: NEEDS REVISION")
            self.nstage_flag_label.setStyleSheet(
                "QLabel { background-color: #ffebee; color: #b71c1c; padding: 6px; "
                "border: 1px solid #ef5350; border-radius: 4px; font-weight: bold; }"
            )
        else:
            self.nstage_flag_label.setText("N-stage review: correct match")
            self.nstage_flag_label.setStyleSheet(
                "QLabel { background-color: #e8f5e9; color: #1b5e20; padding: 6px; "
                "border: 1px solid #66bb6a; border-radius: 4px; font-weight: bold; }"
            )
    
    def _update_ehr_display(self, patient_id):
        """Update EHR UI widgets for the current patient"""
        if not self.ehr_fieldnames or not self.ehr_widgets:
            return
        
        if not patient_id:
            for field, widget in self.ehr_widgets.items():
                if isinstance(widget, QLineEdit):
                    widget.blockSignals(True)
                    widget.clear()
                    widget.blockSignals(False)
                elif isinstance(widget, QComboBox):
                    widget.blockSignals(True)
                    widget.clear()
                    for display_text, stored_value in self._t_stage_options():
                        widget.addItem(display_text, stored_value)
                    widget.setCurrentIndex(-1)
                    widget.blockSignals(False)
                elif isinstance(widget, QLabel):
                    widget.setText("")
            if self.ehr_status_label is not None:
                self.ehr_status_label.setText("")
            if self.nstage_flag_label is not None:
                self.nstage_flag_label.setText("N-stage review: --")
                self.nstage_flag_label.setStyleSheet(
                    "QLabel { background-color: #eeeeee; color: #424242; padding: 6px; "
                    "border: 1px solid #bdbdbd; border-radius: 4px; font-weight: bold; }"
                )
            return
        
        entry = self._ensure_patient_ehr_entry(patient_id)
        if entry is None:
            for field, widget in self.ehr_widgets.items():
                if isinstance(widget, QLineEdit):
                    widget.blockSignals(True)
                    widget.clear()
                    widget.blockSignals(False)
                elif isinstance(widget, QComboBox):
                    widget.blockSignals(True)
                    widget.clear()
                    for display_text, stored_value in self._t_stage_options():
                        widget.addItem(display_text, stored_value)
                    widget.setCurrentIndex(-1)
                    widget.blockSignals(False)
                elif isinstance(widget, QLabel):
                    widget.setText("")
            if self.ehr_status_label is not None:
                self.ehr_status_label.setText("EHR entry unavailable.")
            self._set_nstage_flag_display(None)
            return
        
        for field, widget in self.ehr_widgets.items():
            raw_value = entry.get(field, "")
            display_value = "" if raw_value is None else str(raw_value)
            if isinstance(widget, QLineEdit):
                widget.blockSignals(True)
                widget.setText(display_value)
                widget.blockSignals(False)
            elif isinstance(widget, QComboBox):
                widget.blockSignals(True)
                widget.clear()
                for display_text, stored_value in self._t_stage_options():
                    widget.addItem(display_text, stored_value)
                storage_value = self._normalize_t_stage_choice(raw_value)
                index = widget.findData(storage_value)
                if index == -1 and storage_value:
                    widget.addItem(display_value, storage_value)
                    index = widget.count() - 1
                widget.setCurrentIndex(index if index >= 0 else -1)
                widget.blockSignals(False)
            elif isinstance(widget, QLabel):
                widget.setText(display_value)
        
        if self.ehr_status_label is not None:
            self.ehr_status_label.setText(f"Loaded EHR for patient {patient_id}")
        self._set_nstage_flag_display(entry)
    
    def _on_ehr_value_changed(self, field_name):
        """Handle updates to editable EHR fields."""
        if not self.current_patient_id:
            return
        
        entry = self._ensure_patient_ehr_entry(self.current_patient_id)
        if entry is None:
            return
        
        widget = self.ehr_widgets.get(field_name)
        old_value = "" if entry.get(field_name, "") is None else str(entry.get(field_name, ""))
        if isinstance(widget, QLineEdit):
            new_value = widget.text().strip()
        elif isinstance(widget, QComboBox):
            new_value = widget.currentData()
            if new_value is None:
                new_value = widget.currentText().strip()
            new_value = str(new_value).strip()
        else:
            return

        if new_value == old_value:
            return

        entry[field_name] = new_value

        widget.blockSignals(True)
        if isinstance(widget, QLineEdit):
            widget.setText(new_value)
        elif isinstance(widget, QComboBox):
            index = widget.findData(new_value)
            if index >= 0:
                widget.setCurrentIndex(index)
        widget.blockSignals(False)
        
        self.ehr_modified = True
        self._write_ehr_csv(force_save=True)
        if self.ehr_status_label is not None:
            self.ehr_status_label.setText(f"Updated {field_name} for {self.current_patient_id}")
        if field_name == self.ehr_old_n_stage_field:
            self._set_nstage_flag_display(entry)
    
    def _get_patients(self):
        """Get patient IDs from local finals_not_refined/ masks, ordered by completion status."""
        if not os.path.isdir(self.preprocessed_masks_folder):
            raise ValueError(f"Source mask folder not found: {self.preprocessed_masks_folder}")
        patient_ids = []
        data_files = list_relative_files(self.data_folder)
        skipped_missing_images = []

        def strip_nii_ext(filename):
            if filename.endswith(".nii.gz"):
                return filename[:-7]
            if filename.endswith(".nii"):
                return filename[:-4]
            return os.path.splitext(filename)[0]

        for filename in sorted(os.listdir(self.preprocessed_masks_folder)):
            if not filename.lower().endswith((".nii.gz", ".nii")):
                continue
            patient_id = strip_nii_ext(filename)
            if "_ct" in patient_id.lower() or "_pet" in patient_id.lower() or "__pt" in patient_id.lower():
                continue
            if patient_id in EXCLUDED_SOURCE_MASK_PATIENT_IDS:
                print(f"Skipping {patient_id}: excluded source mask.")
                continue
            has_ct = any(candidate in data_files for candidate in self._ct_candidate_names(patient_id))
            has_pt = any(candidate in data_files for candidate in self._pt_candidate_names(patient_id))
            if has_ct and has_pt:
                patient_ids.append(patient_id)
            else:
                skipped_missing_images.append(patient_id)

        print(f"Using {len(patient_ids)} patients with source masks from {self.preprocessed_masks_folder}")
        if skipped_missing_images:
            print(
                f"Skipped {self.preprocessed_masks_subdir} masks without matching CT/PET files: "
                + ", ".join(skipped_missing_images[:20])
                + ("..." if len(skipped_missing_images) > 20 else "")
            )
        if not patient_ids:
            print(
                f"No patients discovered. Ensure {self.preprocessed_masks_folder} "
                "contains NIfTI mask files with matching CT and PET files in the data folder."
            )

        patient_ids = sorted(patient_ids)
        all_patient_count = len(patient_ids)
        if self.annotator_id != "ALL" and patient_ids:
            annotator_index = int(self.annotator_id) - 1
            total_annotators = 4
            group_size = int(np.ceil(all_patient_count / total_annotators))
            start_idx = annotator_index * group_size
            end_idx = min(start_idx + group_size, all_patient_count)
            patient_ids = patient_ids[start_idx:end_idx]
            print(
                f"Annotator {self.annotator_id} assigned {len(patient_ids)} of "
                f"{all_patient_count} cases."
            )
        elif self.annotator_id == "ALL":
            print(f"ALL mode showing all {all_patient_count} cases.")
        
        # Get completed patients (by this annotator)
        completed_patients = self._get_completed_patients_static()
        
        # Separate completed and incomplete patients
        incomplete_patients = [pid for pid in patient_ids if pid not in completed_patients]
        complete_patients = [pid for pid in patient_ids if pid in completed_patients]
        
        # Sort each group separately, then combine (incomplete first)
        incomplete_patients.sort()
        complete_patients.sort()
        
        return incomplete_patients + complete_patients
    
    def _get_completed_patients_static(self):
        """Patient IDs that already have a saved mask in last_batch/."""
        if not os.path.isdir(self.refined_masks_folder):
            return set()
        completed = set()
        for filename in os.listdir(self.refined_masks_folder):
            if filename.endswith(".nii.gz"):
                completed.add(filename[:-7])
            elif filename.endswith(".nii"):
                completed.add(filename[:-4])
        return completed
    
    def _get_completed_patients(self):
        """Get list of completed patients (those with a saved mask in last_batch/)"""
        return {
            pid for pid in getattr(self, "patients", [])
            if exists_path(self._join_finals(f"{pid}.nii.gz"))
        }
    
    def _update_progress_bar(self):
        """Update the progress bar based on completed patients by this annotator"""
        if not self.patients:
            self.progress_bar.setValue(0)
            self.progress_label.setText(f"Progress ({self.annotator_id}): 0/0 (0%)")
            return
        
        completed_count = len(self.completed_patients)
        total_count = len(self.patients)
        percentage = int((completed_count / total_count) * 100) if total_count > 0 else 0
        
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(f"Progress ({self.annotator_id}): {completed_count}/{total_count} ({percentage}%)")
    
    def _has_unsaved_changes(self):
        """Check if there are unsaved changes in the current patient"""
        if not hasattr(self, 'mask_layer') or self.mask_layer is None:
            return False
        if not hasattr(self, 'original_mask') or self.original_mask is None:
            return False
        
        try:
            current_mask = self.mask_layer.data
            if current_mask is None:
                return False
            return not np.array_equal(current_mask, self.original_mask)
        except Exception as e:
            print(f"Error checking unsaved changes: {e}")
            return False
    
    def _show_unsaved_changes_dialog(self, action_description="continue", custom_warning_msg=None):
        """Show dialog warning about unsaved changes and return user choice
        
        Args:
            action_description: Description of the action being taken (e.g., "moving to the next patient")
            custom_warning_msg: Optional custom warning message to display instead of default
        """
        # If custom warning message is provided, always show dialog
        # Otherwise, only show if there are unsaved changes
        if custom_warning_msg is None and not self._has_unsaved_changes():
            return "continue"  # No changes, safe to continue
        
        # Ensure we have a valid window reference
        if not hasattr(self, 'viewer') or not hasattr(self.viewer, 'window'):
            print("Warning: Cannot show dialog - viewer window not available")
            return "continue"
        
        msg_box = QMessageBox(self.viewer.window._qt_window)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("⚠️ Warning")
        msg_box.setModal(True)  # Ensure dialog is modal
        
        # Use custom warning message if provided, otherwise use default
        if custom_warning_msg:
            msg_box.setText(custom_warning_msg)
            msg_box.setInformativeText(
                f"What would you like to do?\n\n"
                "• Continue: Discard changes and proceed\n"
                "• Stay: Cancel and remain on current patient"
            )
        else:
            msg_box.setText(
                f"You have unsaved segmentation changes for patient: {self.current_patient_id}"
            )
            msg_box.setInformativeText(
                f"Your segmentation has not been saved.\n\n"
                f"What would you like to do?\n\n"
                "• Continue: Discard changes and proceed\n"
                "• Stay: Cancel and remain on current patient"
            )
        
        # Create custom buttons
        continue_button = msg_box.addButton("Continue", QMessageBox.AcceptRole)
        stay_button = msg_box.addButton("Stay", QMessageBox.RejectRole)
        
        # Set default button to Stay (safest option - prevents accidental data loss)
        msg_box.setDefaultButton(stay_button)
        
        # Execute dialog (this blocks until user responds)
        result = msg_box.exec_()
        clicked_button = msg_box.clickedButton()
        
        if clicked_button == continue_button:
            # Continue without saving - discard changes
            return "continue"
        elif clicked_button == stay_button:
            return "stay"
        else:
            # Default: stay on current patient
            return "stay"
    
    def _create_windowing_controls(self, layout):
        """Create CT windowing controls and add to layout"""
        # CT Windowing section
        layout.addWidget(QLabel("<b>CT Windowing:</b>"))
        
        windowing_layout = QHBoxLayout()
        
        # Windowing preset dropdown
        windowing_layout.addWidget(QLabel("Preset:"))
        self.windowing_combo = QComboBox()
        self.windowing_combo.addItems(list(self.CT_WINDOWING_PRESETS.keys()))
        self.windowing_combo.setCurrentText("Soft Tissue")
        self.windowing_combo.currentTextChanged.connect(self._apply_windowing_preset)
        windowing_layout.addWidget(self.windowing_combo)
        
        # Manual window/level controls
        manual_layout = QVBoxLayout()
        
        # Window width control
        window_layout = QHBoxLayout()
        window_layout.addWidget(QLabel("W:"))
        self.window_spinbox = QSpinBox()
        self.window_spinbox.setRange(1, 4000)
        self.window_spinbox.setValue(350)
        self.window_spinbox.setSingleStep(50)
        self.window_spinbox.valueChanged.connect(self._apply_manual_windowing)
        window_layout.addWidget(self.window_spinbox)
        manual_layout.addLayout(window_layout)
        
        # Level control
        level_layout = QHBoxLayout()
        level_layout.addWidget(QLabel("L:"))
        self.level_spinbox = QSpinBox()
        self.level_spinbox.setRange(-1000, 3000)
        self.level_spinbox.setValue(40)
        self.level_spinbox.setSingleStep(10)
        self.level_spinbox.valueChanged.connect(self._apply_manual_windowing)
        level_layout.addWidget(self.level_spinbox)
        manual_layout.addLayout(level_layout)
        
        windowing_layout.addLayout(manual_layout)
        
        # Reset button
        reset_windowing_btn = QPushButton("Reset to Auto")
        reset_windowing_btn.clicked.connect(self._reset_windowing)
        reset_windowing_btn.setStyleSheet("QPushButton { background-color: #9E9E9E; color: white; padding: 2px; }")
        windowing_layout.addWidget(reset_windowing_btn)
        
        layout.addLayout(windowing_layout)

    def _apply_windowing_preset(self, preset_name):
        """Apply a predefined windowing preset to the CT layer"""
        if not hasattr(self, 'ct_layer'):
            return
        
        preset = self.CT_WINDOWING_PRESETS.get(preset_name)
        
        if preset is None:  # Auto contrast
            self._reset_windowing()
            return
        
        window = preset["window"]
        level = preset["level"]
        
        # Calculate contrast limits from window/level
        contrast_min = level - window / 2
        contrast_max = level + window / 2
        
        # Apply to CT layer
        self.ct_layer.contrast_limits = [contrast_min, contrast_max]
        
        # Update manual controls to match preset
        self.window_spinbox.blockSignals(True)
        self.level_spinbox.blockSignals(True)
        self.window_spinbox.setValue(window)
        self.level_spinbox.setValue(level)
        self.window_spinbox.blockSignals(False)
        self.level_spinbox.blockSignals(False)
        
        print(f"Applied {preset_name} windowing: Window={window}, Level={level}")

    def _apply_manual_windowing(self):
        """Apply manual window/level settings"""
        if not hasattr(self, 'ct_layer'):
            return
        
        window = self.window_spinbox.value()
        level = self.level_spinbox.value()
        
        # Calculate contrast limits
        contrast_min = level - window / 2
        contrast_max = level + window / 2
        
        # Apply to CT layer
        self.ct_layer.contrast_limits = [contrast_min, contrast_max]
        
        # Update dropdown to show matching preset if any
        self.windowing_combo.blockSignals(True)
        
        # Check if current settings match any preset
        current_settings = {"window": window, "level": level}
        matching_preset = None
        for preset_name, preset_values in self.CT_WINDOWING_PRESETS.items():
            if preset_values and preset_values == current_settings:
                matching_preset = preset_name
                break
        
        if matching_preset:
            self.windowing_combo.setCurrentText(matching_preset)
        
        self.windowing_combo.blockSignals(False)

    def _reset_windowing(self):
        """Reset windowing to auto-contrast"""
        if not hasattr(self, 'ct_layer'):
            return
        
        # Recalculate auto contrast
        ct_data = self.ct_layer.data
        auto_limits = self._auto_contrast(ct_data)
        self.ct_layer.contrast_limits = auto_limits
        
        # Update controls
        self.windowing_combo.blockSignals(True)
        self.windowing_combo.setCurrentText("Auto")
        self.windowing_combo.blockSignals(False)
        
        print("Reset to auto-contrast windowing")
    
    def _create_ui(self):
        """Create custom UI widgets"""
        # Create a scroll area to contain all controls
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # No horizontal scroll
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)     # Vertical scroll as needed
        
        # Set minimum and maximum dimensions for the scroll area
        scroll_area.setMinimumWidth(500)  # Increased to fit text content better
        scroll_area.setMinimumHeight(400)  # Set minimum height to ensure scrolling works
        
        # Style the scroll area (minimal styling, keep original background)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                background-color: #e0e0e0;
                width: 12px;
                border-radius: 6px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        # Create a container widget for the content
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
        layout.setSpacing(8)  # Add consistent spacing between elements
        
        # Annotator info section
        annotator_info = QLabel(f"<b>Annotator: {self.annotator_id}</b>")
        annotator_info.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                color: #1976d2;
                padding: 4px;
                border: 2px solid #1976d2;
                border-radius: 5px;
                font-size: 10px;
            }
        """)
        annotator_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(annotator_info)
        
        # Progress Section
        layout.addWidget(QLabel("<b>Progress:</b>"))
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                width: 20px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Progress label
        self.progress_label = QLabel(f"Progress ({self.annotator_id}): 0/0 (0%)")
        self.progress_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.progress_label)
        
        # Update progress bar
        self._update_progress_bar()
        
        # Patient Navigation
        layout.addWidget(QLabel("<b>Patient Navigation:</b>"))
        
        # Patient selection
        patient_select_layout = QHBoxLayout()
        patient_select_layout.addWidget(QLabel("Select Patient:"))
        
        self.patient_combo = QComboBox()
        if self.patients:
            self.patient_combo.addItems(self.patients)
            self.patient_combo.currentIndexChanged.connect(self._on_patient_selected)
        else:
            self.patient_combo.addItem("No patients found")
            self.patient_combo.setEnabled(False)
        
        patient_select_layout.addWidget(self.patient_combo)
        layout.addLayout(patient_select_layout)
        
        # Info label for current patient
        self.patient_label = QLabel("No patient loaded")
        layout.addWidget(self.patient_label)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Previous Patient")
        self.prev_btn.clicked.connect(self._prev_patient)
        self.prev_btn.setEnabled(False)
        
        self.next_btn = QPushButton("Next Patient")
        self.next_btn.clicked.connect(self._next_patient)
        self.next_btn.setEnabled(len(self.patients) > 0)
        
        self.save_btn = QPushButton("Save Segmentation")
        self.save_btn.clicked.connect(self._save_mask)
        self.save_btn.setEnabled(False)
        
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        nav_layout.addWidget(self.save_btn)
        layout.addLayout(nav_layout)

        self.ehr_widgets = {}
        self._create_ehr_summary_section(layout)
        # show raw EHR fields and omit the staging review tabs.
        
        # Add CT windowing controls
        self._create_windowing_controls(layout)
        
        # Drawing tools section
        layout.addWidget(QLabel("<b>Drawing Tools:</b>"))
        
        # Tool selection
        tools_layout = QHBoxLayout()
        
        # Tool selection
        tool_label = QLabel("Mouse Mode:")
        self.tool_combo = QComboBox()
        self.tool_combo.addItems(["Paint", "Erase", "Fill", "Pan/Zoom"])
        self.tool_combo.currentTextChanged.connect(self._change_tool)
        
        # Brush size
        brush_label = QLabel("Brush Size:")
        self.brush_slider = QSlider(Qt.Horizontal)
        self.brush_slider.setMinimum(1)
        self.brush_slider.setMaximum(50)
        self.brush_slider.setValue(10)
        self.brush_slider.valueChanged.connect(self._change_brush_size)
        
        tools_layout.addWidget(tool_label)
        tools_layout.addWidget(self.tool_combo)
        tools_layout.addWidget(brush_label)
        tools_layout.addWidget(self.brush_slider)
        layout.addLayout(tools_layout)

        # View controls section
        layout.addWidget(QLabel("<b>View Controls:</b>"))
        view_controls_layout = QHBoxLayout()

        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.clicked.connect(lambda: self._zoom_view(1.25))

        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.clicked.connect(lambda: self._zoom_view(0.8))

        self.fit_view_btn = QPushButton("Fit View")
        self.fit_view_btn.clicked.connect(self._reset_view)

        view_controls_layout.addWidget(self.zoom_in_btn)
        view_controls_layout.addWidget(self.zoom_out_btn)
        view_controls_layout.addWidget(self.fit_view_btn)
        layout.addLayout(view_controls_layout)

        # Measurement tools section
        layout.addWidget(QLabel("<b>Measurement:</b>"))
        measurement_layout = QHBoxLayout()

        self.ruler_btn = QPushButton("Ruler")
        self.ruler_btn.setCheckable(True)
        self.ruler_btn.toggled.connect(self._set_ruler_active)
        self.ruler_btn.setEnabled(False)
        self.ruler_btn.setStyleSheet("QPushButton { background-color: #00BCD4; color: white; font-weight: bold; padding: 3px; }")

        self.clear_ruler_btn = QPushButton("Clear Ruler")
        self.clear_ruler_btn.clicked.connect(self._clear_measurements)
        self.clear_ruler_btn.setEnabled(False)

        measurement_layout.addWidget(self.ruler_btn)
        measurement_layout.addWidget(self.clear_ruler_btn)
        layout.addLayout(measurement_layout)

        self.measurement_label = QLabel("Diameter: -- mm")
        self.measurement_label.setWordWrap(True)
        self.measurement_label.setStyleSheet(
            "QLabel { background-color: #e0f7fa; color: #006064; padding: 4px; border: 1px solid #00acc1; border-radius: 4px; }"
        )
        layout.addWidget(self.measurement_label)
        
        # Smart Interpolation section
        layout.addWidget(QLabel("<b>Smart Interpolation:</b>"))
        
        # Smart interpolation button
        smart_interp_layout = QHBoxLayout()
        self.smart_interpolate_btn = QPushButton("Smart Interpolate")
        self.smart_interpolate_btn.clicked.connect(self._smart_interpolate)
        self.smart_interpolate_btn.setEnabled(False)
        self.smart_interpolate_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; padding: 3px; }")
        
        # Morphological cleanup
        self.cleanup_btn = QPushButton("Clean Up")
        self.cleanup_btn.clicked.connect(self._cleanup_segmentation)
        self.cleanup_btn.setEnabled(False)
        
        smart_interp_layout.addWidget(self.smart_interpolate_btn)
        smart_interp_layout.addWidget(self.cleanup_btn)
        layout.addLayout(smart_interp_layout)

        # Reset/Clear section
        layout.addWidget(QLabel("<b>Reset Options:</b>"))
        
        reset_layout = QHBoxLayout()
        
        # Reload original mask button
        self.reload_original_btn = QPushButton("Reload Original")
        self.reload_original_btn.clicked.connect(self._reload_original_mask)
        self.reload_original_btn.setEnabled(False)
        self.reload_original_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; font-weight: bold; padding: 3px; }")
        
        # Clear button (with enhanced warning)
        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_segmentation)
        self.clear_btn.setEnabled(False)
        self.clear_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 3px; }")
        
        reset_layout.addWidget(self.reload_original_btn)
        reset_layout.addWidget(self.clear_btn)
        layout.addLayout(reset_layout)

        layout.addWidget(QLabel("<b>HECKTOR SEGMENTATION PROTOCOL:</b>"))
        
        # Instructions with detailed protocol guidelines
        instructions_text = (
            "REFINEMENT ORDER:\n"
            "1. Start with GTVp (label 1), then review GTVn (label 2)\n"
            "2. Use CT first for anatomy and PET second for metabolic support\n"
            "3. Save only after checking every edited slice\n\n"

            "GTVp REFINEMENT - Primary Tumor (label 1):\n"
            "• Include ENTIRE edges of morphologic anomaly on CT\n"
            "• Include corresponding hypermetabolic volume on PET\n"
            "• Use PET/CT fusion for accurate delineation\n"
            "• Remove air pockets, airway lumen, bone, teeth, vessels, and normal fat\n"
            "• Remove spillover uptake that extends beyond the CT tumor boundary\n"
            "• Smooth jagged edges while preserving true tumor extent\n"
            "• EXCLUDE hypermetabolic activity outside physical limits\n"
            "• EXCLUDE nearby FDG-avid lymph nodes\n"
            "• Check for tonsillectomy/biopsy history (exclude if extensive)\n\n"
            
            "GTVn REFINEMENT - Metastatic Lymph Nodes (label 2):\n"
            "• Include entire morphologic lymphadenopathy on CT\n"
            "• Include corresponding hypermetabolic volume on PET\n"
            "• Criteria: SUV>2.5 OR diameter ≥1cm OR pathologically confirmed\n"
            "• Remove vessels, muscle, salivary glands, thyroid, bone, and dental artifact\n"
            "• Keep nodal masks separate from GTVp; do not bridge across normal tissue\n"
            "• Remove isolated specks that do not correspond to a lymph node\n"
            "• EXCLUDE activity on bony/muscular/vascular structures\n"
            "• If nodes touch/merge: keep as one structure\n"
            "• GTVn and GTVp must be SEPARATED\n\n"

            "T-STAGING QUICK REFERENCE (Oropharynx):\n"
            "• T0: no GTVp mask / no primary tumor mask visible\n"
            "• T1: tumor 2 cm or less in greatest dimension\n"
            "• T2: tumor > 2 cm but not > 4 cm in greatest dimension\n"
            "• T3: tumor > 4 cm, or extension to lingual surface of epiglottis\n"
            "• T4a: moderately advanced local disease with invasion of larynx, extrinsic tongue muscle, medial pterygoid, hard palate, or mandible\n"
            "• T4b: very advanced local disease with invasion of lateral pterygoid muscle/plates, lateral nasopharynx, skull base, or carotid encasement\n"
            "• Select T4 for either T4a or T4b in the editable EHR field\n"
            "• Mucosal extension to lingual epiglottis from base of tongue/vallecula does not count as larynx invasion\n"
            "• Use the Ruler on the greatest dimension when updating T-stage\n\n"
            
            "WORKFLOW:\n"
            "1. Review CT for morphologic changes\n"
            "2. Review PET for hypermetabolic areas\n"
            "3. Adjust CT windowing as needed\n"
            "4. Edit segmentation masks if needed\n"
            "5. Use 'Ruler' to measure tumor diameter when needed\n"
            "6. Use 'Smart Interpolate' to fill gaps\n"
            "7. Use 'Clean Up' to refine results\n"
            "8. Verify separation between GTVp and GTVn\n"
            f"9. Save final segmentation to {self.refined_masks_subdir}/"
        )
        
        instructions_label = QLabel(instructions_text)
        instructions_label.setWordWrap(True)
        instructions_label.setStyleSheet(
            "QLabel { "
            "background-color: #f0f8ff; "
            "color: #333333; "
            "padding: 6px; "
            "border: 1px solid #cccccc; "
            "border-radius: 5px; "
            "font-size: 11px; "
            "line-height: 1.2; "
            "}"
        )
        layout.addWidget(instructions_label)
        
        # Logo section (if logo path provided) - remove the stretch before this
        if self.logo_path and os.path.exists(self.logo_path):
            logo_label = QLabel()
            logo_pixmap = QPixmap(self.logo_path)
            # Scale logo to reasonable size (max 150px width for bottom placement)
            if logo_pixmap.width() > 250:
                logo_pixmap = logo_pixmap.scaledToWidth(250, Qt.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setStyleSheet(
                "QLabel { "
                "margin-top: 15px; "
                "margin-bottom: 10px; "
                "border-top: 1px solid #cccccc; "
                "padding-top: 8px; "
                "}"
            )
            layout.addWidget(logo_label)
        
        # Ensure the container has a minimum height for proper scrolling
        container.setMinimumHeight(800)  # Set minimum height to trigger scrolling
        
        # Set the container as the scroll area's widget
        scroll_area.setWidget(container)
        
        # Add the scroll area to the viewer instead of the container
        self.viewer.window.add_dock_widget(scroll_area, name="HECKTOR Tools", area="right")
    
    def _create_ruler_layer(self):
        """Create a line-shape layer used for diameter measurements."""
        self.ruler_layer = self.viewer.add_shapes(
            data=[],
            ndim=3,
            name="Ruler",
            shape_type="line",
            edge_color="cyan",
            edge_width=4,
            face_color="transparent",
            opacity=1.0,
            properties={"measurement": []},
            text={
                "string": "{measurement}",
                "size": 12,
                "color": "cyan",
                "anchor": "upper_left",
                "translation": [0, 0, 8],
            },
            scale=(self.ct_spacing[2], self.ct_spacing[1], self.ct_spacing[0]),
        )
        self.ruler_layer.mode = "pan_zoom"
        self.ruler_layer.events.data.connect(self._update_measurement_display)
        self._update_measurement_display()

    def _set_ruler_active(self, enabled, restore_mask=True):
        """Toggle line drawing for tumor diameter measurement."""
        self.ruler_active = bool(enabled)

        if hasattr(self, "ruler_btn"):
            self.ruler_btn.blockSignals(True)
            self.ruler_btn.setChecked(self.ruler_active)
            self.ruler_btn.setText("Ruler On" if self.ruler_active else "Ruler")
            self.ruler_btn.blockSignals(False)

        if not hasattr(self, "ruler_layer") or self.ruler_layer is None:
            return

        if self.ruler_active:
            self.viewer.layers.selection.active = self.ruler_layer
            self._ruler_data_count_at_activation = len(self.ruler_layer.data)
            self.ruler_layer.mode = "add_line"
            if hasattr(self, "measurement_label"):
                self.measurement_label.setText("Diameter: draw a line across the tumor")
        else:
            self.ruler_layer.mode = "pan_zoom"
            if restore_mask and hasattr(self, "mask_layer") and self.mask_layer is not None:
                self._apply_segmentation_tool(self.tool_combo.currentText())
            self._update_measurement_display()

    def _clear_measurements(self):
        """Remove all ruler measurements for the current patient."""
        if not hasattr(self, "ruler_layer") or self.ruler_layer is None:
            return
        self.ruler_layer.data = []
        self._ruler_data_count_at_activation = 0
        self._update_measurement_display()

    def _measurement_spacing(self, ndim):
        """Return layer-coordinate spacing in mm for the given number of dims."""
        full_spacing = np.array(
            [self.ct_spacing[2], self.ct_spacing[1], self.ct_spacing[0]],
            dtype=np.float32,
        )
        return full_spacing[-ndim:]

    def _measurement_length_mm(self, line):
        """Measure a ruler line in physical millimeters."""
        points = np.asarray(line, dtype=np.float32)
        if points.ndim != 2 or points.shape[0] < 2:
            return None
        start = points[0]
        end = points[-1]
        spacing = self._measurement_spacing(points.shape[1])
        return float(np.linalg.norm((end - start) * spacing))

    def _update_measurement_display(self, event=None):
        """Update the tumor diameter readout from ruler lines."""
        if not hasattr(self, "measurement_label"):
            return
        if not hasattr(self, "ruler_layer") or self.ruler_layer is None:
            self.measurement_label.setText("Diameter: -- mm")
            return

        measurements = []
        panel_labels = []
        canvas_labels = []
        for index, line in enumerate(self.ruler_layer.data, start=1):
            length_mm = self._measurement_length_mm(line)
            canvas_labels.append(str(index))
            if length_mm is not None:
                measurements.append(length_mm)
                panel_labels.append(f"{index}: {length_mm:.1f} mm")
            else:
                panel_labels.append(f"{index}: -- mm")

        self.ruler_layer.properties = {
            "measurement": np.asarray(canvas_labels, dtype=object),
        }

        if not measurements:
            self.measurement_label.setText("Diameter: -- mm")
            self.ruler_layer.name = "Ruler"
            return

        latest = measurements[-1]
        max_length = max(measurements)
        label_text = "Diameters:\n" + "\n".join(panel_labels)
        label_text += f"\nMax: {max_length:.1f} mm"
        self.measurement_label.setText(label_text)
        self.ruler_layer.name = f"Ruler ({latest:.1f} mm)"

        if (
            getattr(self, "ruler_active", False)
            and len(self.ruler_layer.data) > self._ruler_data_count_at_activation
        ):
            self._set_ruler_active(False)
    
    def _on_patient_selected(self, index):
        """Handle patient selection from dropdown with unsaved changes check"""
        if index >= 0 and index < len(self.patients) and index != self.current_patient_idx:
            # Check for unsaved changes before switching
            choice = self._show_unsaved_changes_dialog("switching to selected patient")
            
            if choice == "continue":
                self.current_patient_idx = index
                self.load_patient(self.patients[index])
            else:
                # Revert dropdown selection if user cancelled
                self.patient_combo.blockSignals(True)
                self.patient_combo.setCurrentIndex(self.current_patient_idx)
                self.patient_combo.blockSignals(False)
    
    def _update_patient_info(self):
        """Update UI based on currently loaded patient"""
        if self.current_patient_idx >= 0 and self.current_patient_idx < len(self.patients):
            patient_id = self.patients[self.current_patient_idx]
            
            # Check if patient is completed by this annotator
            completion_status = " ✓" if patient_id in self.completed_patients else ""
            self.patient_label.setText(f"Current Patient: {patient_id}{completion_status}")
            
            # Update dropdown selection
            self.patient_combo.blockSignals(True)
            self.patient_combo.setCurrentIndex(self.current_patient_idx)
            self.patient_combo.blockSignals(False)
            
            # Enable buttons
            self.prev_btn.setEnabled(True)
            self.next_btn.setEnabled(True)
            self.save_btn.setEnabled(True)
            self.smart_interpolate_btn.setEnabled(True)
            self.cleanup_btn.setEnabled(True)
            self.clear_btn.setEnabled(True)
            self.reload_original_btn.setEnabled(True)
            self.ruler_btn.setEnabled(True)
            self.clear_ruler_btn.setEnabled(True)
            self._update_ehr_display(patient_id)
            self._update_tstage_display(patient_id)
        else:
            self.patient_label.setText("No patient loaded")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(len(self.patients) > 0)
            self.save_btn.setEnabled(False)
            self.smart_interpolate_btn.setEnabled(False)
            self.cleanup_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
            self.reload_original_btn.setEnabled(False)
            self.ruler_btn.setEnabled(False)
            self.clear_ruler_btn.setEnabled(False)
            self._update_ehr_display(None)
            self._update_tstage_display(None)
    
    def _smart_interpolate(self):
        """Advanced interpolation using morphological operations and PET guidance for multi-class labels"""
        if not hasattr(self, 'mask_layer'):
            return
            
        # Get current mask data
        mask_data = self.mask_layer.data.copy()
        
        # Find slices that have segmentation
        segmented_slices = []
        for i in range(mask_data.shape[0]):
            if np.any(mask_data[i] > 0):
                segmented_slices.append(i)
        
        if len(segmented_slices) < 2:
            QMessageBox.warning(
                self.viewer.window._qt_window,
                "Insufficient Data",
                "Need at least 2 slices with segmentation to interpolate.\n"
                "Draw segmentation on a few key slices first."
            )
            return
        
        # Get unique labels
        unique_labels = np.unique(mask_data[mask_data > 0])
        print(f"Smart interpolating between slices: {segmented_slices}")
        print(f"Found label classes: {unique_labels}")
        
        # Get the PT image for guidance
        pt_data = self.pt_layer.data
        
        # Create interpolated mask
        interpolated_mask = mask_data.copy()
        
        # Process each gap between segmented slices
        for i in range(len(segmented_slices) - 1):
            start_slice = segmented_slices[i]
            end_slice = segmented_slices[i + 1]
            
            if end_slice - start_slice > 1:
                print(f"Processing gap: slice {start_slice} to {end_slice}")
                
                # Interpolate each label class separately
                for label_value in unique_labels:
                    if label_value == 0:  # Skip background
                        continue
                    
                    # Extract label-specific masks
                    start_label_mask = (mask_data[start_slice] == label_value)
                    end_label_mask = (mask_data[end_slice] == label_value)
                    
                    # Only interpolate if this label exists in both slices
                    if np.any(start_label_mask) and np.any(end_label_mask):
                        # Use advanced interpolation method for this label
                        interpolated_slices = self._advanced_interpolate_gap_multiclass(
                            start_label_mask, 
                            end_label_mask,
                            pt_data[start_slice:end_slice+1],
                            end_slice - start_slice - 1,
                            label_value
                        )
                        
                        # Insert interpolated slices for this label
                        for j, interp_slice in enumerate(interpolated_slices):
                            slice_idx = start_slice + 1 + j
                            # Add this label to the slice (preserving other labels)
                            interpolated_mask[slice_idx][interp_slice] = label_value
                    
                    # Handle cases where label exists in only one slice
                    elif np.any(start_label_mask) or np.any(end_label_mask):
                        print(f"Label {label_value} exists in only one slice - using simpler interpolation")
                        # Use distance-based fade out/in
                        active_mask = start_label_mask if np.any(start_label_mask) else end_label_mask
                        for j in range(end_slice - start_slice - 1):
                            slice_idx = start_slice + 1 + j
                            alpha = (j + 1) / (end_slice - start_slice)
                            
                            if np.any(start_label_mask):
                                # Fade out from start
                                fade_mask = (gaussian(active_mask.astype(float), sigma=1.0) > (0.3 + 0.4 * alpha))
                            else:
                                # Fade in to end
                                fade_mask = (gaussian(active_mask.astype(float), sigma=1.0) > (0.7 - 0.4 * alpha))
                            
                            interpolated_mask[slice_idx][fade_mask] = label_value
        
        # Update the mask layer
        self.mask_layer.data = interpolated_mask
        
        print("Smart interpolation complete!")
        QMessageBox.information(
            self.viewer.window._qt_window,
            "Smart Interpolation Complete",
            f"Interpolated between {len(segmented_slices)} slices for {len(unique_labels)} label classes\n"
            f"Classes: {list(unique_labels)}\n"
            "Use 'Clean Up' to refine the results."
        )
    
    def _advanced_interpolate_gap_multiclass(self, start_mask, end_mask, pt_slices, num_slices, label_value):
        """Advanced interpolation for a specific label class using multiple techniques"""
        interpolated_slices = []
        
        # Convert to binary float for this specific label
        start_binary = start_mask.astype(float)
        end_binary = end_mask.astype(float)
        
        for i in range(num_slices):
            alpha = (i + 1) / (num_slices + 1)
            
            # Method 1: Distance transform interpolation
            start_dist = ndimage.distance_transform_edt(start_binary == 0) - \
                        ndimage.distance_transform_edt(start_binary > 0)
            end_dist = ndimage.distance_transform_edt(end_binary == 0) - \
                      ndimage.distance_transform_edt(end_binary > 0)
            
            interp_dist = (1 - alpha) * start_dist + alpha * end_dist
            distance_mask = (interp_dist <= 0).astype(float)
            
            # Method 2: Morphological interpolation
            start_smooth = gaussian(start_binary, sigma=2.0)
            end_smooth = gaussian(end_binary, sigma=2.0)
            morph_mask = ((1 - alpha) * start_smooth + alpha * end_smooth > 0.3).astype(float)
            
            # Method 3: PET-guided interpolation (adapt threshold based on label)
            current_pt = pt_slices[i + 1]
            # Use different PET thresholds for different labels
            if label_value == 1:
                # Primary tumor - higher PET uptake
                pt_threshold = np.percentile(current_pt[current_pt > 0], 80) if np.any(current_pt > 0) else 0
            else:
                # Secondary structures - moderate PET uptake
                pt_threshold = np.percentile(current_pt[current_pt > 0], 60) if np.any(current_pt > 0) else 0
            
            pt_mask = (current_pt > pt_threshold).astype(float) if pt_threshold > 0 else np.zeros_like(current_pt)
            
            # Combine methods with weights (adjust based on label)
            if label_value == 1:
                # For primary tumor, rely more on distance and PET
                combined_mask = 0.4 * distance_mask + 0.2 * morph_mask + 0.4 * pt_mask
                threshold = 0.4
            else:
                # For other structures, rely more on morphological interpolation
                combined_mask = 0.5 * distance_mask + 0.4 * morph_mask + 0.1 * pt_mask
                threshold = 0.3
            
            # Apply threshold
            final_mask = (combined_mask > threshold).astype(bool)
            
            # Clean up with morphological operations (gentle for multi-class)
            if np.any(final_mask):
                final_mask = morphology.binary_opening(final_mask, morphology.disk(1))
                final_mask = morphology.binary_closing(final_mask, morphology.disk(2))
                final_mask = morphology.remove_small_objects(final_mask, min_size=25)
            
            interpolated_slices.append(final_mask)
        
        return interpolated_slices
    
    def _cleanup_segmentation(self):
        """Clean up segmentation using morphological operations while preserving label classes"""
        if not hasattr(self, 'mask_layer'):
            return
            
        mask_data = self.mask_layer.data.copy()
        cleaned_mask = np.zeros_like(mask_data)
        
        print("Cleaning up segmentation while preserving label classes...")
        
        # Get unique labels (excluding background)
        unique_labels = np.unique(mask_data[mask_data > 0])
        print(f"Found label classes: {unique_labels}")
        
        for i in range(mask_data.shape[0]):
            slice_mask = mask_data[i]
            
            if np.any(slice_mask > 0):
                slice_cleaned = np.zeros_like(slice_mask)
                
                # Process each label class separately
                for label_value in unique_labels:
                    if label_value == 0:  # Skip background
                        continue
                        
                    # Extract current label
                    label_mask = (slice_mask == label_value)
                    
                    if np.any(label_mask):
                        # Apply morphological operations to this label class
                        # Remove small objects
                        label_mask = morphology.remove_small_objects(
                            label_mask, 
                            min_size=20  # Reduced from 30 to preserve smaller structures
                        )
                        
                        # Fill small holes
                        label_mask = morphology.remove_small_holes(
                            label_mask, 
                            area_threshold=50  # Reduced from 100
                        )
                        
                        # Smooth boundaries (gentler operations)
                        label_mask = morphology.binary_opening(label_mask, morphology.disk(1))
                        label_mask = morphology.binary_closing(label_mask, morphology.disk(2))
                        
                        # Add cleaned label back to slice with original label value
                        slice_cleaned[label_mask] = label_value
                
                cleaned_mask[i] = slice_cleaned
        
        self.mask_layer.data = cleaned_mask
        print(f"Cleanup complete! Preserved {len(unique_labels)} label classes: {unique_labels}")
    
    def _reload_original_mask(self):
        """Reload the original mask from when the patient was first loaded"""
        if not hasattr(self, 'mask_layer') or not hasattr(self, 'original_mask'):
            QMessageBox.warning(
                self.viewer.window._qt_window,
                "No Original Mask",
                "No original mask available to reload."
            )
            return
            
        # Show confirmation dialog
        reply = QMessageBox.question(
            self.viewer.window._qt_window,
            "Reload Original Mask",
            "Are you sure you want to reload the original mask?\n\n"
            "⚠️ WARNING: This will discard ALL current changes!\n"
            "• All manual edits will be lost\n"
            "• Smart interpolation results will be lost\n"
            "• Cleanup operations will be lost\n\n"
            "Consider saving your current work first if needed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Reload original mask
            self.mask_layer.data = self.original_mask.copy()
            print("Original mask reloaded")
            QMessageBox.information(
                self.viewer.window._qt_window,
                "Original Mask Reloaded",
                "The original mask has been restored.\nAll modifications have been discarded."
            )
    
    def _clear_segmentation(self):
        """Clear all segmentation with enhanced warning"""
        if not hasattr(self, 'mask_layer'):
            return
        
        # Enhanced warning dialog with more details
        reply = QMessageBox.question(
            self.viewer.window._qt_window,
            "⚠️ CLEAR ALL SEGMENTATION",
            "🚨 <b>DANGER: This will permanently delete ALL segmentation!</b>\n\n"
            "<b>What will be lost:</b>\n"
            "• All manual annotations (GTVp and GTVn)\n"
            "• Smart interpolation results\n"
            "• Cleanup operations\n"
            "• All drawing/editing work\n\n"
            "<b>This action cannot be undone!</b>\n\n"
            "💡 <b>Alternative:</b> Use 'Reload Original' instead if you want to\n"
            "    go back to the original segmentation without losing everything.\n\n"
            "Are you absolutely sure you want to clear ALL segmentation?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Additional confirmation for destructive action
            final_reply = QMessageBox.warning(
                self.viewer.window._qt_window,
                "Final Confirmation",
                "⚠️ LAST CHANCE TO CANCEL ⚠️\n\n"
                "You are about to delete ALL segmentation work.\n"
                "This cannot be undone!\n\n"
                "Proceed with clearing everything?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel
            )
            
            if final_reply == QMessageBox.Yes:
                empty_mask = np.zeros_like(self.mask_layer.data)
                self.mask_layer.data = empty_mask
                print("All segmentation cleared")
                QMessageBox.information(
                    self.viewer.window._qt_window,
                    "Segmentation Cleared",
                    "All segmentation has been cleared.\nYou can start fresh or reload the original mask."
                )
    
    def load_patient(self, patient_id):
        """Load data for a specific patient"""
        self.current_patient_id = patient_id

        # Extract base patient ID and variant suffix
        # e.g., "CHUB-030_whole_body" -> base="CHUB-030", suffix="_whole_body"
        base_patient_id = self.get_base_patient_id(patient_id)
        variant_suffix = self._variant_suffix_for_patient(patient_id)
        
        # Paths to possible mask locations:
        # 1) last_batch folder (previous saved output, if any)
        # 2) finals_not_refined folder (source masks)
        mask_filename = f"{patient_id}.nii.gz"
        refined_mask_file = self._join_finals(mask_filename)
        preprocessed_mask_file = self._join_preprocessed_masks(mask_filename)
        if exists_path(refined_mask_file):
            mask_reference_file = refined_mask_file
        elif exists_path(preprocessed_mask_file):
            mask_reference_file = preprocessed_mask_file
        else:
            mask_reference_file = None

        # Support both the current validation layout:
        #   PATIENT/PATIENT__CT.nii.gz, PATIENT/PATIENT__PT.nii.gz
        # and older flat staging layouts used by previous annotation batches.
        # For unsuffixed masks, select the cropped/whole_body image pair by
        # testing which CT grid the source mask actually overlaps.
        ct_file, ct_paths_tried, pt_file, pt_paths_tried = self._select_ct_pt_files(
            patient_id,
            mask_reference_file,
        )
        print(f"Using CT file candidate: {ct_file}")
        print(f"Using PT file candidate: {pt_file}")

        original_mask_candidates = [
            ("finals_not_refined", preprocessed_mask_file),
        ]
        
        # Check if files exist
        if not exists_path(ct_file):
            QMessageBox.warning(self.viewer.window._qt_window, 
                                "File Not Found", 
                                "CT scan for patient "
                                f"{patient_id} not found.\n\nTried:\n"
                                + "\n".join(ct_paths_tried))
            return
        
        if not exists_path(pt_file):
            QMessageBox.warning(self.viewer.window._qt_window, 
                                "File Not Found", 
                                f"PET scan for patient {patient_id} not found.\n\nTried:\n"
                                + "\n".join(pt_paths_tried) + "\n\n"
                                f"Base patient ID: {base_patient_id}\n"
                                f"Variant suffix: {variant_suffix}")
            return
        
        print(f"Loading patient {patient_id}...")
        
        # Load CT image using nibabel
        ct_array, ct_spacing, ct_affine = read_image_nib(ct_file)
        # Store spacing/affine for later use (mask saving, scaling)
        # Note: we follow previous convention: spacing = (x, y, z)
        self.ct_spacing = ct_spacing
        self.ct_affine = ct_affine
        
        # Load PT image using nibabel
        pt_array, pt_spacing, pt_affine = read_image_nib(pt_file)
        
        # Resample PT to CT grid (spacing + affine) using nibabel to improve alignment
        try:
            if self.ct_affine is not None:
                # Build nib images in (x, y, z) order
                ct_ref_img = nib.Nifti1Image(np.transpose(ct_array, (2, 1, 0)), self.ct_affine)
                pt_img = nib.Nifti1Image(np.transpose(pt_array, (2, 1, 0)), pt_affine if pt_affine is not None else np.eye(4, dtype=np.float32))
                resampled_pt_img = nproc.resample_from_to(pt_img, (ct_ref_img.shape, ct_ref_img.affine), order=1)
                resampled_pt = resampled_pt_img.get_fdata().astype(np.float32)
                # Back to (z, y, x)
                pt_array = np.transpose(resampled_pt, (2, 1, 0))
                pt_spacing = ct_spacing
                print(f"Resampled PT to CT grid for patient {patient_id}")
            else:
                # Fallback to spacing-based zoom if affine missing
                zoom_factors = (
                    pt_spacing[2] / ct_spacing[2],
                    pt_spacing[1] / ct_spacing[1],
                    pt_spacing[0] / ct_spacing[0],
                )
                if any(abs(f - 1.0) > 1e-3 for f in zoom_factors):
                    print(f"Resampling PT to CT spacing for patient {patient_id} with zoom {zoom_factors}...")
                    pt_array = ndimage.zoom(pt_array, zoom=zoom_factors, order=1)
                    pt_spacing = ct_spacing
        except Exception as _exc:
            print(f"Warning: PT resampling to CT grid failed ({_exc}); using original PT spacing.")

        # Convert canonical arrays into the expected axial display orientation.
        ct_array = self._to_display_orientation(ct_array)
        pt_array = self._to_display_orientation(pt_array)
        
        # Clear viewer
        self.viewer.layers.clear()
        self.ruler_layer = None
        self.ruler_active = False
        if hasattr(self, "ruler_btn"):
            self.ruler_btn.blockSignals(True)
            self.ruler_btn.setChecked(False)
            self.ruler_btn.setText("Ruler")
            self.ruler_btn.blockSignals(False)
        if hasattr(self, "measurement_label"):
            self.measurement_label.setText("Diameter: -- mm")
        
        # Add CT as base layer
        self.ct_layer = self.viewer.add_image(
            ct_array, 
            name="CT",
            scale=(self.ct_spacing[2], self.ct_spacing[1], self.ct_spacing[0]),
            colormap='gray',
            contrast_limits=self._auto_contrast(ct_array)
        )
        
        # Apply default soft-tissue windowing after creating CT layer.
        if hasattr(self, 'windowing_combo'):
            self.windowing_combo.setCurrentText("Soft Tissue")
            self._apply_windowing_preset("Soft Tissue")
        
        # CHANGE 3: Modified PET scan to use inferno colormap instead of hot
        # Use PT spacing for display (z, y, x order for napari scale)
        self.pt_layer = self.viewer.add_image(
            pt_array,
            name="PT",
            scale=(pt_spacing[2], pt_spacing[1], pt_spacing[0]),
            colormap='inferno',  # Changed from 'hot' to 'inferno'
            blending="additive",
            opacity=0.7,
            contrast_limits=self._auto_contrast(pt_array)
        )
        
        # Load and add mask if available.
        # Logic:
        #   1) Try last_batch/{patient_id}.nii.gz, so reopened work resumes.
        #   2) If that fails, fall back to finals_not_refined/{patient_id}.nii.gz.
        #   3) If both are missing, create an empty mask.
        mask_array = None
        mask_file_used = None
        mask_affine = None

        # First try the last_batch output folder.
        if exists_path(refined_mask_file):
            try:
                mask_array, _, mask_affine = read_image_nib(refined_mask_file)
                mask_file_used = refined_mask_file
                print(f"Loading existing last_batch segmentation for patient {patient_id}")
            except Exception as exc:
                print(f"Failed to load last_batch mask from {refined_mask_file}: {exc}")
                mask_array = None
                mask_affine = None

        # If last_batch output is absent, load the best available source mask.
        if mask_array is None:
            for source_name, original_mask_file in original_mask_candidates:
                if not exists_path(original_mask_file):
                    continue
                try:
                    mask_array, _, mask_affine = read_image_nib(original_mask_file)
                    mask_file_used = original_mask_file
                    print(f"Loading source {source_name} segmentation for patient {patient_id}")
                    break
                except Exception as exc:
                    print(f"Failed to load original mask from {original_mask_file}: {exc}")
                    mask_array = None
                    mask_affine = None

        if mask_array is None:
            print(f"Warning: No mask found for patient {patient_id}; starting with empty mask.")
            # Create empty mask with same dimensions as CT
            mask_array = np.zeros_like(ct_array, dtype=np.uint8)
            mask_file_used = None
        else:
            mask_array = self._resample_mask_to_ct_grid(
                mask_array,
                mask_affine,
                ct_array,
                patient_id,
                mask_file_used,
            )
            mask_array = self._to_display_orientation(mask_array)
            # Ensure integer type for napari Labels layer
            mask_array = mask_array.astype(np.uint8)
        
        # Store original mask for comparison and reloading
        self.original_mask = mask_array.copy()
        
        # Create the mask layer
        self.mask_layer = self.viewer.add_labels(
            mask_array,
            name="Segmentation",
            scale=(self.ct_spacing[2], self.ct_spacing[1], self.ct_spacing[0]),
            opacity=0.5
        )
        self._create_ruler_layer()
        
        # Save file paths for later use
        self.ct_file = ct_file
        self.pt_file = pt_file
        self.mask_file = mask_file_used
        
        # Set mask as active layer for drawing
        self.viewer.layers.selection.active = self.mask_layer
        self._change_tool(self.tool_combo.currentText())
        
        # Update UI
        self._update_patient_info()
        self._update_ehr_display(patient_id)
        self._update_tstage_display(patient_id)
        
        print(f"Patient {patient_id} loaded successfully")
    
    def _register_pt_to_ct(self, pt_image, ct_image):
        """
        Dummy PT->CT registration function kept for backward compatibility.
        
        We no longer use SimpleITK-based resampling here to avoid native DLL
        dependencies on Windows. PT is loaded and displayed directly in CT's
        space using its own spacing.
        """
        print("PT registration is disabled (using nibabel-based loading instead).")
        return pt_image
    
    def _auto_contrast(self, image, p_low=0.5, p_high=99.5):
        """Automatically determine contrast limits for better visualization"""
        # Exclude zeros (background) from percentile calculation
        non_zeros = image[image > 0]
        if len(non_zeros) > 0:
            low = np.percentile(non_zeros, p_low)
            high = np.percentile(non_zeros, p_high)
        else:
            low, high = np.min(image), np.max(image)
        
        # Ensure we have a valid range
        if low >= high:
            high = low + 1
            
        return [low, high]
    
    def _apply_segmentation_tool(self, tool_name):
        """Apply the selected labels-layer editing mode."""
        if not hasattr(self, 'mask_layer'):
            return

        if tool_name == "Pan/Zoom":
            self.viewer.layers.selection.active = self.mask_layer
            self.viewer.layers.selection.active.mode = 'pan_zoom'
        elif tool_name == "Paint":
            self.viewer.layers.selection.active = self.mask_layer
            self.viewer.layers.selection.active.mode = 'paint'
        elif tool_name == "Erase":
            self.viewer.layers.selection.active = self.mask_layer
            self.viewer.layers.selection.active.mode = 'erase'
        elif tool_name == "Fill":
            self.viewer.layers.selection.active = self.mask_layer
            self.viewer.layers.selection.active.mode = 'fill'

    def _change_tool(self, tool_name):
        """Change the active segmentation tool"""
        if getattr(self, "ruler_active", False):
            self._set_ruler_active(False, restore_mask=False)
        self._apply_segmentation_tool(tool_name)
        if hasattr(self, "brush_slider"):
            self.brush_slider.setEnabled(tool_name != "Pan/Zoom")

    def _zoom_view(self, factor):
        """Zoom the central napari canvas by a fixed multiplier."""
        if not hasattr(self, "viewer") or self.viewer is None:
            return
        try:
            current_zoom = float(self.viewer.camera.zoom)
            if current_zoom <= 0:
                current_zoom = 1.0
            self.viewer.camera.zoom = current_zoom * factor
        except Exception as exc:
            print(f"Failed to zoom view: {exc}")

    def _reset_view(self):
        """Reset the central napari canvas to fit the loaded layers."""
        if not hasattr(self, "viewer") or self.viewer is None:
            return
        try:
            self.viewer.reset_view()
        except Exception as exc:
            print(f"Failed to reset view: {exc}")
    
    def _change_brush_size(self, size):
        """Change brush size for painting/erasing"""
        if hasattr(self, 'mask_layer'):
            self.mask_layer.brush_size = size
    
    def _save_mask(self):
        """Save the segmentation to the local last_batch/ folder."""
        if not hasattr(self, 'mask_layer') or self.current_patient_id is None:
            return

        # Get final mask data
        final_mask = self.mask_layer.data
        
        # Undo the display-only vertical flip before saving in CT/NIfTI orientation.
        final_mask = self._from_display_orientation(final_mask)
        
        # Create NIfTI image for mask with CT affine (orientation/spacing)
        # Note: final_mask is (z, y, x); nibabel expects (x, y, z)
        if hasattr(self, "ct_affine") and self.ct_affine is not None:
            mask_data_nib = np.transpose(final_mask, (2, 1, 0)).astype(np.float32)
            mask_img = nib.Nifti1Image(mask_data_nib, self.ct_affine)
        else:
            # Fallback: identity affine
            mask_data_nib = np.transpose(final_mask, (2, 1, 0)).astype(np.float32)
            mask_img = nib.Nifti1Image(mask_data_nib, np.eye(4, dtype=np.float32))
        
        filename = f"{self.current_patient_id}.nii.gz"
        output_file = self._join_finals(filename)
        try:
            os.makedirs(self.finals_folder, exist_ok=True)
            nib.save(mask_img, output_file)
        except Exception as e:
            QMessageBox.warning(
                self.viewer.window._qt_window,
                "Save Failed",
                f"Failed to save segmentation:\n{str(e)}\n\nPath: {output_file}"
            )
            return

        # If we get here, save was successful
        # Update the original mask to reflect the saved state
        self.original_mask = self.mask_layer.data.copy()
        
        # Update completed patients and progress bar
        self.completed_patients.add(self.current_patient_id)
        self._update_progress_bar()
        self._update_patient_info()  # Update to show completion checkmark
        
        # Save EHR changes if any were made
        self._write_ehr_csv(force_save=True)
        
        print(f"Saved segmentation for patient {self.current_patient_id} by {self.annotator_id} to {output_file}")
        
        # Show confirmation message
        QMessageBox.information(self.viewer.window._qt_window, 
                              "Save Successful", 
                              f"Saved segmentation for patient {self.current_patient_id}\n"
                              f"File: {self.refined_masks_subdir}/{self.current_patient_id}.nii.gz\n"
                              f"Location: {output_file}\n"
                              f"Annotator: {self.annotator_id}")
    
    def _next_patient(self):
        """Load the next patient with unsaved changes check"""
        if not self.patients:
            return
        
        # Check if patient has been saved (file exists in last_batch folder)
        if self.current_patient_id:
            saved_mask_path = self._join_finals(f"{self.current_patient_id}.nii.gz")
            has_saved_file = exists_path(saved_mask_path)
            
            # Check for unsaved changes
            has_changes = self._has_unsaved_changes()
            
            # Warn if: there are unsaved changes OR no saved file exists
            if has_changes or not has_saved_file:
                if has_changes and not has_saved_file:
                    warning_msg = (
                        f"Patient {self.current_patient_id} has unsaved changes "
                        f"and no saved file in last_batch folder.\n\n"
                        f"Your work will be lost if you proceed without saving."
                    )
                elif has_changes:
                    warning_msg = (
                        f"Patient {self.current_patient_id} has unsaved changes.\n\n"
                        f"Your work will be lost if you proceed without saving."
                    )
                else:  # not has_saved_file
                    warning_msg = (
                        f"Patient {self.current_patient_id} has not been saved yet.\n\n"
                        f"No file found in last_batch folder. Your work will be lost if you proceed without saving."
                    )
                
                choice = self._show_unsaved_changes_dialog("moving to the next patient", custom_warning_msg=warning_msg)
                if choice != "continue":
                    print("User chose to stay on current patient")
                    return  # User chose to stay or cancelled
            else:
                # Patient is saved and no changes - safe to proceed
                print(f"Patient {self.current_patient_id} is saved with no changes, proceeding to next")
                choice = "continue"
        else:
            choice = "continue"
        
        if choice == "continue":
            self.current_patient_idx = (self.current_patient_idx + 1) % len(self.patients)
            self.load_patient(self.patients[self.current_patient_idx])
        # If cancelled, stay with current patient
    
    def _prev_patient(self):
        """Load the previous patient with unsaved changes check"""
        if not self.patients:
            return
        
        # Check if patient has been saved (file exists in last_batch folder)
        if self.current_patient_id:
            saved_mask_path = self._join_finals(f"{self.current_patient_id}.nii.gz")
            has_saved_file = exists_path(saved_mask_path)
            
            # Check for unsaved changes
            has_changes = self._has_unsaved_changes()
            
            # Warn if: there are unsaved changes OR no saved file exists
            if has_changes or not has_saved_file:
                if has_changes and not has_saved_file:
                    warning_msg = (
                        f"Patient {self.current_patient_id} has unsaved changes "
                        f"and no saved file in last_batch folder.\n\n"
                        f"Your work will be lost if you proceed without saving."
                    )
                elif has_changes:
                    warning_msg = (
                        f"Patient {self.current_patient_id} has unsaved changes.\n\n"
                        f"Your work will be lost if you proceed without saving."
                    )
                else:  # not has_saved_file
                    warning_msg = (
                        f"Patient {self.current_patient_id} has not been saved yet.\n\n"
                        f"No file found in last_batch folder. Your work will be lost if you proceed without saving."
                    )
                
                choice = self._show_unsaved_changes_dialog("moving to the previous patient", custom_warning_msg=warning_msg)
                if choice != "continue":
                    print("User chose to stay on current patient")
                    return  # User chose to stay or cancelled
            else:
                # Patient is saved and no changes - safe to proceed
                print(f"Patient {self.current_patient_id} is saved with no changes, proceeding to previous")
                choice = "continue"
        else:
            choice = "continue"
        
        if choice == "continue":
            self.current_patient_idx = (self.current_patient_idx - 1) % len(self.patients)
            self.load_patient(self.patients[self.current_patient_idx])
        # If cancelled, stay with current patient


def get_annotator_id():
    """Get annotator ID through login dialog"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # Don't quit when dialog closes
    
    print("Showing annotator selection dialog...")
    login_dialog = AnnotatorLoginDialog()
    login_dialog.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Dialog)  # Keep on top
    login_dialog.show()  # Explicitly show the dialog
    login_dialog.raise_()  # Bring to front
    login_dialog.activateWindow()  # Activate the window
    
    # Process events to ensure dialog is displayed
    app.processEvents()
    
    result = login_dialog.exec_()
    
    if result == QDialog.Accepted:
        annotator_id = login_dialog.get_annotator_id()
        print(f"Annotator ID selected: {annotator_id}")
        return annotator_id
    else:
        print("Annotator selection cancelled")
        return None


def main():
    # Parse command line arguments
    args = parse_args()
    
    # Use data folder from arguments
    data_folder = args.data
    if not os.path.isdir(data_folder):
        print(f"Data folder '{data_folder}' does not exist. Please provide a valid path.")
        sys.exit(1)
    
    # Optional: Path to logo image
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    
    print("Starting HECKTOR Annotation Tool...")
    raw_annotator_id = str(args.annotator).strip().upper() if args.annotator else get_annotator_id()
    if raw_annotator_id is None:
        print("No annotator selected. Exiting.")
        sys.exit(0)
    if raw_annotator_id.isdigit():
        annotator_id = str(int(raw_annotator_id))
    else:
        annotator_id = raw_annotator_id
    
    print(f"Starting annotation session for: {annotator_id}")
    
    # Create the viewer with annotator ID
    viewer = HECKTORViewer(
        data_folder,
        annotator_id,
        logo_path=logo_path,
        tstage_csv_path=args.tstage_csv,
    )
    
    # If specific patient requested (from web interface), load it
    if args.patient and args.patient in viewer.patients:
        patient_index = viewer.patients.index(args.patient)
        viewer.current_patient_idx = patient_index
        viewer.load_patient(args.patient)
        print(f"Loaded patient: {args.patient}")
    
    # Start the napari event loop
    napari.run()

# MAKE SURE this is at the very end of your file:
if __name__ == "__main__":
    main()
