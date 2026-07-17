#!/usr/bin/env bash
# Generate styled .docx (and optionally PDF) for one or all application folders.
#
# Usage:
#   scripts/make_pdfs.sh applications/<company>_<title>
#   scripts/make_pdfs.sh --all
#
# Output per folder:
#   resume.docx / cover_letter.docx   — Word format matching the original resume style
#   resume.pdf  / cover_letter.pdf    — PDF via xelatex (plain but fast)
#
# For submission-quality PDFs that exactly match the Word formatting, open the
# .docx in Word and use File → Save As → PDF, or run scripts/word_to_pdf.ps1
# from Windows PowerShell (not from WSL).

set -euo pipefail
cd "$(dirname "$0")/.."

REF_DOCX="data/pandoc_reference.docx"

convert_dir() {
  local dir="$1"
  if [ -f "$dir/resume.md" ]; then
    pandoc "$dir/resume.md" -t plain -o "$dir/resume.txt"
    echo "wrote $dir/resume.txt"
    pandoc "$dir/resume.md" --reference-doc="$REF_DOCX" -o "$dir/resume.docx"
    echo "wrote $dir/resume.docx"
    pandoc "$dir/resume.md" -o "$dir/resume.pdf" \
      --pdf-engine=xelatex -V geometry:margin=0.75in -V fontsize=10pt -V colorlinks=true
    echo "wrote $dir/resume.pdf"
  fi
  if [ -f "$dir/cover_letter.md" ]; then
    pandoc "$dir/cover_letter.md" -t plain -o "$dir/cover_letter.txt"
    echo "wrote $dir/cover_letter.txt"
    pandoc "$dir/cover_letter.md" --reference-doc="$REF_DOCX" -o "$dir/cover_letter.docx"
    echo "wrote $dir/cover_letter.docx"
    pandoc "$dir/cover_letter.md" -o "$dir/cover_letter.pdf" \
      --pdf-engine=xelatex -V geometry:margin=1in -V fontsize=11pt -V colorlinks=true
    echo "wrote $dir/cover_letter.pdf"
  fi
}

if [ "${1:-}" = "--all" ]; then
  for dir in applications/*/; do
    convert_dir "${dir%/}"
  done
else
  if [ -z "${1:-}" ]; then
    echo "Usage: $0 <applications/company_title> | --all" >&2
    exit 1
  fi
  convert_dir "${1%/}"
fi
