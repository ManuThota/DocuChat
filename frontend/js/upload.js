/**
 * frontend/js/upload.js — File upload controller with card-based document UI.
 */

import { UploadAPI, ChatAPI } from './api.js';

export function initUpload({ dropZone, fileInput, filesPanel, activeDocBadge, activeDocName, showToast, onUpload, getActiveChatId, onNewChatCreated }) {
  let activeFileId = null;

  // ─── Delete modal state ───────────────────────────────────────────────────
  let pendingDeleteId   = null;
  let pendingDeleteName = null;
  let pendingChatId     = null;

  const deleteOverlay  = document.getElementById('docDeleteOverlay');
  const deleteNameEl   = document.getElementById('docDeleteName');
  const deleteConfirm  = document.getElementById('docDeleteConfirm');
  const deleteCancel   = document.getElementById('docDeleteCancel');

  if (deleteCancel)  deleteCancel.addEventListener('click',  closeDeleteModal);
  if (deleteOverlay) deleteOverlay.addEventListener('click', (e) => { if (e.target === deleteOverlay) closeDeleteModal(); });
  if (deleteConfirm) deleteConfirm.addEventListener('click', async () => {
    if (!pendingDeleteId) return;
    try {
      await UploadAPI.deleteFile(pendingDeleteId);
      showToast('Document deleted', 'info');
      if (pendingDeleteId === activeFileId) {
        activeFileId = null;
        activeDocBadge.style.display = 'none';
      }
      closeDeleteModal();
      if (pendingChatId) await loadFilesForChat(pendingChatId);
    } catch (err) {
      showToast(`Failed to delete: ${err.message}`, 'error');
      closeDeleteModal();
    }
  });

  function openDeleteModal(id, name, chatId) {
    pendingDeleteId   = id;
    pendingDeleteName = name;
    pendingChatId     = chatId;
    if (deleteNameEl) deleteNameEl.textContent = name;
    if (deleteOverlay) deleteOverlay.classList.add('open');
  }

  function closeDeleteModal() {
    pendingDeleteId = null;
    if (deleteOverlay) deleteOverlay.classList.remove('open');
  }

  // ─── Drag-and-drop events ─────────────────────────────────────────────────
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });

  // ─── File input change ────────────────────────────────────────────────────
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) uploadFile(fileInput.files[0]);
    fileInput.value = '';
  });

  // ─── Upload logic ─────────────────────────────────────────────────────────
  // ─── Upload logic ─────────────────────────────────────────────────────────
  async function uploadFile(file) {
    let chatId = getActiveChatId ? getActiveChatId() : null;
    if (!chatId) {
      try {
        const chat = await ChatAPI.newChat();
        chatId = chat.id;
        if (onNewChatCreated) await onNewChatCreated(chat);
      } catch (err) {
        showToast('Failed to create chat for upload.', 'error');
        return;
      }
    }

    // Show progress-bar placeholder in the grid
    const placeholder = document.createElement('div');
    placeholder.className = 'doc-card uploading';
    placeholder.innerHTML = `
      <div class="upload-progress-container">
        <div class="upload-progress-bar" style="width: 0%"></div>
      </div>
      <div class="upload-text">Processing document...</div>
      <div class="doc-card-name" style="font-size:10px; margin-top:4px;">${file.name}</div>
    `;
    
    const grid = filesPanel.querySelector('.doc-cards-grid');
    if (grid) grid.appendChild(placeholder);
    else {
      filesPanel.innerHTML = '<div class="doc-cards-grid"></div>';
      filesPanel.querySelector('.doc-cards-grid').appendChild(placeholder);
    }

    const progressBar = placeholder.querySelector('.upload-progress-bar');

    try {
      const result = await UploadAPI.uploadFileWithProgress(file, chatId, (percent) => {
        // Cap visual progress at 95% until server actually finishes processing
        const visualPercent = Math.min(percent, 95);
        progressBar.style.width = `${visualPercent}%`;
      });
      
      // Complete the bar only when server response is received
      progressBar.style.width = '100%';
      
      activeFileId = result.id;
      localStorage.setItem('docuchat_active_file_id', result.id);
      localStorage.setItem('docuchat_active_file_name', result.original_name);

      activeDocName.textContent = result.original_name;
      activeDocBadge.style.display = 'flex';
      dropZone.classList.remove('visible');

      showToast(`${result.original_name} uploaded successfully`, 'success');
      onUpload(result);
      await loadFilesForChat(chatId);
    } catch (err) {
      showToast(`Upload failed: ${err.message}`, 'error');
      await loadFilesForChat(chatId);
    }
  }

  function restore() {
    const savedId = localStorage.getItem('docuchat_active_file_id');
    const savedName = localStorage.getItem('docuchat_active_file_name');
    if (savedId && savedName) {
      activeFileId = parseInt(savedId);
      activeDocName.textContent = savedName;
      activeDocBadge.style.display = 'flex';
      return activeFileId;
    }
    return null;
  }


  // ─── Load files for a specific chat ──────────────────────────────────────
  let currentLoadChatId = null;
  async function loadFilesForChat(chatId) {
    currentLoadChatId = chatId;
    try {
      const allFiles = await UploadAPI.listFiles();
      // Ensure we only render if this is still the active chat
      if (currentLoadChatId !== chatId) return;

      const files = chatId ? allFiles.filter(f => f.chat_id === chatId) : [];

      if (!files.length) {
        filesPanel.innerHTML = '<div class="doc-empty">No documents in this chat yet.</div>';
        return;
      }
      renderDocCards(files, chatId);
    } catch (_) { /* silently ignore */ }
  }

  // ─── Render document cards ────────────────────────────────────────────────
  function renderDocCards(files, chatId) {
    filesPanel.innerHTML = `<div class="doc-cards-grid">${files.map(f => `
      <div class="doc-card ${f.id === activeFileId ? 'selected' : ''}"
           data-id="${f.id}" data-name="${escHtml(f.original_name)}" data-chat="${chatId || ''}">
        <button class="doc-card-delete" data-id="${f.id}" data-name="${escHtml(f.original_name)}" title="Delete document">
          <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
        <div class="doc-card-icon">${fileIconSVG(f.file_type)}</div>
        <div class="doc-card-name" title="${escHtml(f.original_name)}">${escHtml(f.original_name)}</div>
        <div class="doc-card-type">.${f.file_type.toUpperCase()}</div>
      </div>
    `).join('')}</div>`;

    // Select card
    filesPanel.querySelectorAll('.doc-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.doc-card-delete')) return;
        const id   = parseInt(card.dataset.id, 10);
        const name = card.dataset.name;

        if (activeFileId === id) {
          // Deselect
          activeFileId = null;
          activeDocBadge.style.display = 'none';
        } else {
          activeFileId = id;
          activeDocName.textContent = name;
          activeDocBadge.style.display = 'flex';
        }

        filesPanel.querySelectorAll('.doc-card').forEach(c => c.classList.remove('selected'));
        if (activeFileId === id) card.classList.add('selected');
        else card.classList.remove('selected');
      });
    });

    // Delete button
    filesPanel.querySelectorAll('.doc-card-delete').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        openDeleteModal(parseInt(btn.dataset.id, 10), btn.dataset.name, chatId);
      });
    });
  }

  function deselect() {
    activeFileId = null;
    activeDocBadge.style.display = 'none';
  }

  return {
    getActiveFileId: () => activeFileId,
    loadFilesForChat,
    deselect,
    restore,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function truncateName(name) {
  if (name.length <= 14) return name;
  const ext = name.lastIndexOf('.');
  if (ext > 0) {
    const base = name.slice(0, ext);
    const extension = name.slice(ext);
    return base.slice(0, 10) + '…' + extension;
  }
  return name.slice(0, 13) + '…';
}

function fileIconSVG(ext) {
  const isImg = ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext.toLowerCase());
  const color = isImg ? '#34d399' : (ext === 'pdf' ? '#f87171' : '#60a5fa');

  if (isImg) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`;
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
  </svg>`;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
