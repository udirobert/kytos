#!/usr/bin/env bash
# Track 2 — Stage training data onto Nebius persistent disk.
# Run after bootstrap_nebius.sh.
#
# Data sources:
#   - paired_transfer_train.npz + delta_matrix_src.npz: from Modal volume
#     (scp from a machine with modal CLI, or use `modal volume get`)
#   - Raw h5ads: re-download from public URLs (for future GEARS/scGPT work)
#
# Usage: bash tools/track2/stage_data.sh [--with-raw]
set -euo pipefail

DATA_DIR="/data"
RAW_DIR="${DATA_DIR}/raw"
DERIVED_DIR="${DATA_DIR}/derived"

mkdir -p "$RAW_DIR/atlas" "$RAW_DIR/replogle" "$RAW_DIR/vcc2026" "$DERIVED_DIR"

# --- Derived data (required for conditional MLP) ---
echo "=== Staging derived data ==="
echo "Expecting paired_transfer_train.npz and delta_matrix_src.npz in ${DERIVED_DIR}/"
echo ""
echo "Transfer from local machine (run on your laptop):"
echo "  modal volume get kytos-vcc /paired-transfer/paired_transfer_train.npz /tmp/"
echo "  modal volume get kytos-vcc /paired-transfer/delta_matrix_src.npz /tmp/"
echo "  scp /tmp/paired_transfer_train.npz /tmp/delta_matrix_src.npz <nebius-ip>:${DERIVED_DIR}/"
echo ""

# Check if already present
if [ -f "${DERIVED_DIR}/paired_transfer_train.npz" ]; then
    echo "[OK] paired_transfer_train.npz found ($(du -h ${DERIVED_DIR}/paired_transfer_train.npz | cut -f1))"
else
    echo "[MISSING] paired_transfer_train.npz — see transfer instructions above"
fi

if [ -f "${DERIVED_DIR}/delta_matrix_src.npz" ]; then
    echo "[OK] delta_matrix_src.npz found ($(du -h ${DERIVED_DIR}/delta_matrix_src.npz | cut -f1))"
else
    echo "[MISSING] delta_matrix_src.npz — see transfer instructions above"
fi

# --- Raw data (optional, for GEARS / scGPT later) ---
if [[ "${1:-}" == "--with-raw" ]]; then
    echo ""
    echo "=== Staging raw data (for GEARS/scGPT) ==="

    # 2025 Atlas validation
    ATLAS_PATH="${RAW_DIR}/atlas/adata_Validation.h5ad"
    if [ ! -f "$ATLAS_PATH" ]; then
        echo "Downloading Atlas validation (6.5 GB)..."
        curl -L --fail --retry 3 -o "$ATLAS_PATH" \
            "https://storage.googleapis.com/arc-institute-virtual-cell-atlas/virtual-cell-challenge/2025/validation/adata_Validation.h5ad"
    else
        echo "[OK] Atlas already present"
    fi

    # Replogle K562 GWPS
    REPLOGLE_PATH="${RAW_DIR}/replogle/K562_gwps_raw_bulk_01.h5ad"
    if [ ! -f "$REPLOGLE_PATH" ]; then
        echo "Downloading Replogle K562 GWPS (358 MB)..."
        curl -L --fail --retry 3 -o "$REPLOGLE_PATH" \
            "https://ndownloader.figshare.com/files/35774443"
    else
        echo "[OK] Replogle K562 already present"
    fi

    # 2026 VCC controls
    VCC2026_ZIP="${RAW_DIR}/vcc2026/vcc_2026_controls.zip"
    if [ ! -f "$VCC2026_ZIP" ]; then
        echo "Downloading VCC 2026 controls (~660 MB)..."
        echo "NOTE: requires 'vcc datasets download controls' or manual download"
        echo "  vcc datasets download controls"
        echo "  mv vcc_2026_controls.zip ${VCC2026_ZIP}"
    else
        echo "[OK] VCC 2026 controls zip present"
        # Extract if needed
        if [ ! -f "${RAW_DIR}/vcc2026/context_A.h5ad" ]; then
            echo "Extracting contexts..."
            unzip -qo "$VCC2026_ZIP" -d "${RAW_DIR}/vcc2026/"
        fi
    fi
else
    echo ""
    echo "(Skipping raw data. Use --with-raw to also download h5ad files for GEARS/scGPT.)"
fi

echo ""
echo "=== Data staging complete ==="
echo "Derived data in: ${DERIVED_DIR}/"
ls -lh "${DERIVED_DIR}/" 2>/dev/null || true
