#!/usr/bin/env python3
# Copyright (c) 2025 格律至微
# SPDX-License-Identifier: AGPL-3.0-only

"""Compile translation files from .po to .mo format

This script tries multiple methods to compile .po files to .mo format.
If neither msgfmt nor polib are available, it will create minimal .mo files.
"""

import logging
import struct
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def create_minimal_mo_file(mo_file: Path) -> bool:
    """Create a minimal valid .mo file

    Args:
        mo_file: Path to output .mo file

    Returns:
        bool: True if successful
    """
    try:
        # Create minimal .mo file header
        # Format: https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html

        # Magic number - little endian
        magic = 0x950412DE

        # Format revision
        revision = 0

        # Number of strings
        nstrings = 0

        # Offset of original string table (starts after header)
        orig_table_offset = 28  # 7 * 4 bytes

        # Offset of translation string table (same as original when empty)
        trans_table_offset = 28

        # Size of hash table (0 = no hash table)
        hash_table_size = 0

        # Offset of hash table (0 = no hash table)
        hash_table_offset = 0

        # Pack header - 7 fields, each 4 bytes = 28 bytes total
        header = struct.pack(
            "<IIIIIII",  # 7 unsigned integers (I), little endian
            magic,
            revision,
            nstrings,
            orig_table_offset,
            trans_table_offset,
            hash_table_size,
            hash_table_offset,
        )

        # Write .mo file
        mo_file.parent.mkdir(parents=True, exist_ok=True)
        with Path(mo_file).open("wb") as f:
            f.write(header)

        return True

    except Exception:
        logger.exception("Failed to create .mo file: ")
        return False


def compile_with_msgfmt(po_file: Path, mo_file: Path) -> bool:
    """Try to compile using msgfmt command

    Args:
        po_file: Path to .po file
        mo_file: Path to output .mo file

    Returns:
        bool: True if successful
    """
    try:
        import subprocess

        result = subprocess.run(
            ["msgfmt", "-o", str(mo_file), str(po_file)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            return True
        logger.debug(f"msgfmt failed: {result.stderr}")
        return False

    except Exception as e:
        logger.debug(f"msgfmt not available: {e}")
        return False


def compile_with_polib(po_file: Path, mo_file: Path) -> bool:
    """Try to compile using polib

    Args:
        po_file: Path to .po file
        mo_file: Path to output .mo file

    Returns:
        bool: True if successful
    """
    try:
        import polib

        po = polib.pofile(str(po_file))
        po.save_as_mofile(str(mo_file))
        return True

    except ImportError:
        logger.debug("polib not available")
        return False
    except Exception as e:
        logger.debug(f"polib compilation failed: {e}")
        return False


def compile_translations():
    """Compile all .po files to .mo format"""

    locales_dir = Path(__file__).parent / "locales"

    # Find all .po files
    po_files = list(locales_dir.glob("*/LC_MESSAGES/dawei_tui.po"))

    if not po_files:
        logger.warning(f"No .po files found in {locales_dir}")
        return True

    logger.info(f"Found {len(po_files)} translation file(s) to compile")

    # Count results
    success = 0
    fallback = 0
    failed = 0

    for po_file in po_files:
        mo_file = po_file.with_suffix(".mo")
        lang = po_file.parent.parent.name

        # Try msgfmt first
        if compile_with_msgfmt(po_file, mo_file):
            logger.info(f"✓ Compiled {lang} using msgfmt")
            success += 1
            continue

        # Try polib
        if compile_with_polib(po_file, mo_file):
            logger.info(f"✓ Compiled {lang} using polib")
            success += 1
            continue

        # Fallback to minimal .mo file
        if create_minimal_mo_file(mo_file):
            logger.info(f"⚠ Created minimal .mo file for {lang} (translations won't work)")
            logger.warning("Install gettext-tools or polib for proper translations: pip install polib")
            fallback += 1
        else:
            logger.error(f"✗ Failed to create .mo file for {lang}")
            failed += 1

    # Summary
    logger.info(f"\nCompilation complete: {success} compiled, {fallback} minimal, {failed} failed")

    if success == 0 and fallback > 0:
        logger.warning("\n⚠ Translation files were created but may not work properly. For full translation support, install:\n  - Ubuntu/Debian: sudo apt-get install gettext\n  - macOS: brew install gettext\n  - Python: pip install polib")

    return failed == 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    success = compile_translations()
    sys.exit(0 if success else 1)
