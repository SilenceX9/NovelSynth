function setStatus(id, msg) {
  document.getElementById(id).textContent = msg;
}

function showSection(id) {
  document.getElementById(id).style.display = 'block';
}

function getBookId() {
  return localStorage.getItem('book_id');
}

function setBookId(id) {
  localStorage.setItem('book_id', id);
}

// Override upload to save book_id
const origUpload = window.uploadFile;
document.addEventListener('DOMContentLoaded', function() {
  const uploadBtn = document.getElementById('upload-btn');
  if (uploadBtn) {
    uploadBtn.onclick = async function() {
      const file = document.getElementById('file-input').files[0];
      if (!file) return alert('请先选择文件');
      const fd = new FormData();
      fd.append('file', file);
      setStatus('upload-status', '上传中...');
      const res = await fetch('/api/books/upload', { method: 'POST', body: fd });
      const data = await res.json();
      setBookId(data.book_id);
      setStatus('upload-status', '上传成功！book_id: ' + data.book_id);
      showSection('index-section');
    };
  }
});
