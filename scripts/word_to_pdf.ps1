# Convert all resume.docx / cover_letter.docx under applications\ to PDF using Word.
# Run this from Windows PowerShell (NOT from WSL), e.g.:
#   powershell.exe -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu\home\ytmikey\projects\job-search-agent\scripts\word_to_pdf.ps1"
#
# Or open PowerShell on Windows, navigate to the project, and run:
#   .\scripts\word_to_pdf.ps1

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$AppsDir = Join-Path $ProjectDir "applications"

$word = New-Object -ComObject Word.Application
$word.Visible = $false

$docxFiles = Get-ChildItem -Path $AppsDir -Recurse -Include "resume.docx","cover_letter.docx"
foreach ($file in $docxFiles) {
    $pdfPath = [System.IO.Path]::ChangeExtension($file.FullName, "pdf")
    Write-Host "Converting $($file.FullName) ..."
    $doc = $word.Documents.Open($file.FullName)
    $doc.SaveAs2($pdfPath, 17)   # 17 = wdFormatPDF
    $doc.Close()
    Write-Host "  -> $pdfPath"
}

$word.Quit()
Write-Host "Done."
