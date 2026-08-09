from pathlib import Path

root = Path(__file__).resolve().parents[1]
styles_path = root / "src/accessible_caption_studio/web/styles.css"
styles = styles_path.read_text()
marker = "/* Font favorite optical centering */"
if marker not in styles:
    styles += r'''


/* Font favorite optical centering */
.caption-font-option .caption-font-favorite {
  transform: translateY(-1px);
}
'''
styles_path.write_text(styles)
