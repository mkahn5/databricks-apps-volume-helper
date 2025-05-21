# v0.3 Databricks Volume Helper - collaborate with organization non console users - a simple file browser tool on Databricks Apps
# mike.kahn@databricks.com
# To use this app, update lines 18 (host),19 (PAT), 242 (volume path), 243 (volume path 2 (optional))


import os
import requests
import streamlit as st
from PIL import Image, ExifTags
import io
from streamlit_pdf_viewer import pdf_viewer
from streamlit.runtime.scriptrunner import RerunException


# replace host with the Databricks hostname in your url
# replace token with the PAT - more details https://docs.databricks.com/aws/en/dev-tools/auth/pat 
# ─── Constants ────────────────────────────────────────────────────────────────
host = ''
token = ''

image_types = ['png', 'jpg', 'jpeg', 'gif', 'bmp']
text_types  = ['txt', 'text', 'csv', 'json', 'xml']
html_types  = ['html', 'htm']
pdf_types   = ['pdf']
supported_types = image_types + text_types + html_types + pdf_types

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

st.set_page_config(layout="wide")

# ─── CSS Injection ────────────────────────────────────────────────────────────
st.markdown("""
<style>
body {
  font-family: 'SF Pro Display', sans-serif;
  background: #fff;
  color: #222;
  margin: 0;
  padding: 0;
}
header {
  display: flex;
  align-items: center;
  padding: 24px 0 0 32px;
}
.logo {
  height: 28px;
  margin-right: 16px;
}
h1 {
  font-size: 2.2rem;
  font-weight: 600;
  margin: 0 0 8px 0;
}
.subtitle {
  color: #666;
  font-size: 1.1rem;
  margin-bottom: 32px;
}
input[type="text"] {
  width: 420px;
  padding: 10px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 1rem;
  margin-bottom: 24px;
  background: #fafbfc;
}
input[type="text"]:focus {
  outline: 2px solid #0069d9;
  border-color: #0069d9;
}
.container {
  display: flex;
  flex-direction: row;
  gap: 32px;
  margin: 0 32px;
}
.file-list {
  flex: 1;
  background: #f7f8fa;
  border-radius: 10px;
  padding: 24px;
  min-width: 340px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
}
.file-list h2 {
  font-size: 1.1rem;
  font-weight: 500;
  margin-bottom: 18px;
}
.file-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}
.file-card, .folder-card {
  background: #fff;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  padding: 18px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: border 0.2s, box-shadow 0.2s;
}
.file-card.selected, .folder-card.selected {
  border: 2px solid #0069d9;
  box-shadow: 0 2px 8px rgba(0,105,217,0.08);
}
.file-card:hover, .folder-card:hover {
  border: 1.5px solid #0069d9;
}
.file-icon, .folder-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.file-info {
  display: flex;
  flex-direction: column;
}
.file-name, .folder-name {
  font-weight: 500;
  font-size: 1.05rem;
  color: #222;
}
.file-date, .folder-date {
  font-size: 0.92rem;
  color: #888;
  margin-top: 2px;
}
.viewer-pane {
  flex: 2;
  background: #fff;
  border-radius: 10px;
  padding: 32px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.03);
  min-width: 480px;
}
.viewer-pane h3 {
  font-size: 1.1rem;
  font-weight: 500;
  margin-bottom: 10px;
}
.viewer-preview {
  margin-top: 18px;
  background: #f7f8fa;
  border-radius: 8px;
  padding: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
}
.viewer-preview img, .viewer-preview embed, .viewer-preview object {
  max-width: 100%;
  max-height: 320px;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
@media (max-width: 900px) {
  .container {
    flex-direction: column;
    gap: 18px;
  }
  .file-list, .viewer-pane {
    min-width: 0;
    width: 100%;
  }
}
</style>
""", unsafe_allow_html=True)

# ─── Helper Functions ────────────────────────────────────────────────────────
def download_file(path: str) -> bytes | None:
    p = path.lstrip('/')
    resp = requests.get(f"{host}api/2.0/fs/files/{p}", headers=headers, stream=True)
    return resp.content if resp.status_code == 200 else None

def upload_file(path: str, data: bytes) -> bool:
    resp = requests.put(f"{host}api/2.0/fs/files/{path.lstrip('/')}", headers=headers, data=data)
    return 200 <= resp.status_code < 300

def get_file_type(name: str) -> str:
    ext = name.split('.')[-1].lower()
    if ext in image_types: return 'image'
    if ext in text_types:  return 'text'
    if ext in html_types:  return 'html'
    if ext in pdf_types:   return 'pdf'
    return 'unknown'

def correct_image_orientation(img: Image.Image) -> Image.Image:
    try:
        for k,v in ExifTags.TAGS.items():
            if v == 'Orientation':
                orient_key = k
                break
        exif = img._getexif()
        if exif:
            o = exif.get(orient_key)
            if o == 3: img = img.rotate(180, expand=True)
            if o == 6: img = img.rotate(270, expand=True)
            if o == 8: img = img.rotate(90, expand=True)
    except Exception:
        pass
    return img

def build_tree_display(root: str, flat_list: list[str]) -> tuple[list[str], dict[str,str]]:
    labels, mapping = [], {}
    for path in flat_list:
        rel = path.replace(root, "").lstrip("/")
        depth = rel.count("/")
        name = os.path.basename(path.rstrip("/")) + ("/" if path.endswith("/") else "")
        indent = " " * depth
        lbl = f"{indent}{name}"
        labels.append(lbl)
        mapping[lbl] = path
    return labels, mapping

# ─── Main App ────────────────────────────────────────────────────────────────
def main():
    # Header
    st.markdown("""
    <header>
    <h1>UC volume viewer</h1>
    </header>
    <p class="subtitle">
      This app allows you to view, upload, and download files from a Databricks volume
    </p>
    """, unsafe_allow_html=True)

    # Replace volume path with your Databricks volume(s) - https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-volumes 
    # Volume selector
    volumes = [
        "/Volumes/mikekahn-demo/mikekahn/files/",
        "/Volumes/mikekahn-demo/mikekahn/mylife/"
    ]
    if "current_volume" not in st.session_state:
        st.session_state.current_volume = volumes[0]

    sel = st.selectbox(
        "Enter a Unity Catalog Volume name",
        volumes,
        index=volumes.index(st.session_state.current_volume)
    )
    if sel != st.session_state.current_volume:
        st.session_state.current_volume = sel
        st.session_state.file_list = []
        st.session_state.expanded_dirs = set()

    # Container for file-list and viewer
    st.markdown('<div class="container">', unsafe_allow_html=True)
    col1, col2 = st.columns([0.3, 0.7])

    # ── Column 1: File List ────────────────────────────────────────────────
    with col1:
        st.markdown('<div class="file-list">', unsafe_allow_html=True)
        st.markdown("<h2>Files</h2>", unsafe_allow_html=True)

        if "file_list" not in st.session_state:
            st.session_state.file_list = []
        if "expanded_dirs" not in st.session_state:
            st.session_state.expanded_dirs = set()

        def refresh_list():
            r = requests.get(
                f"{host}api/2.0/fs/directories{st.session_state.current_volume}",
                headers=headers
            )
            if r.status_code == 200:
                st.session_state.file_list = [f["path"] for f in r.json().get("contents", [])]
                st.session_state.expanded_dirs.clear()
            else:
                st.error(f"Error fetching file list: {r.status_code}")

        if not st.session_state.file_list:
            refresh_list()

        labels, mapping = build_tree_display(
            st.session_state.current_volume,
            st.session_state.file_list
        )
        choice = st.radio("", [""] + labels, key="file_label")
        st.session_state.file_selector = mapping.get(choice, "")

        st.markdown("---")
        upload = st.file_uploader("Upload local file:")
        if upload:
            dest = st.session_state.current_volume + upload.name
            if upload_file(dest, upload.read()):
                st.success(f"'{upload.name}' uploaded successfully!")
                refresh_list()
                raise RerunException()
            else:
                st.error(f"Failed to upload '{upload.name}'")

        if st.button("Refresh File Listing"):
            refresh_list()

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Column 2: Viewer Pane ─────────────────────────────────────────────
    with col2:
        st.markdown('<div class="viewer-pane">', unsafe_allow_html=True)
        st.markdown("<h3>Preview</h3>", unsafe_allow_html=True)
        st.caption("Supported: .png, .jpg, .html, .pdf, .txt, etc.")

        selected = st.session_state.get("file_selector", "")
        if selected.endswith("/"):
            if selected not in st.session_state.expanded_dirs:
                r = requests.get(f"{host}api/2.0/fs/directories{selected}", headers=headers)
                if r.status_code == 200:
                    st.session_state.expanded_dirs.add(selected)
                    children = r.json().get("contents", [])
                    idx = st.session_state.file_list.index(selected)
                    for i, child in enumerate(children, start=1):
                        p = child["path"]
                        if p not in st.session_state.file_list:
                            st.session_state.file_list.insert(idx + i, p)
                else:
                    st.error(f"Error listing directory: {r.status_code}")
                raise RerunException()

        elif selected:
            data = download_file(selected)
            if not data:
                st.error("Failed to download file.")
                return

            name = os.path.basename(selected)
            ftype = get_file_type(name)

            if ftype == "image":
                img = Image.open(io.BytesIO(data))
                img = correct_image_orientation(img)
                st.image(img, caption=name, use_column_width=True)

            elif ftype == "text":
                st.text_area("File Content", data.decode("utf-8"), height=300)

            elif ftype == "html":
                mode = st.radio("Render as:", ["html", "raw"], key="html_render")
                if mode == "html":
                    st.components.v1.html(data.decode("utf-8"), height=600, scrolling=True)
                else:
                    st.text_area("Raw HTML", data.decode("utf-8"), height=300)

            elif ftype == "pdf":
                pdf_viewer(data, height=600)

            else:
                st.error("Unsupported file type.")

            st.download_button(
                f"Download {name}",
                data=data,
                file_name=name,
                mime="application/octet-stream"
            )
        else:
            st.write("No file or folder selected.")

        st.markdown('</div>', unsafe_allow_html=True)

    # close container
    st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
