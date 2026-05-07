/**
 * frontend/js/dashboard.js — Dashboard main logic.
 */

import { Auth, ChatAPI, UserAPI } from './api.js';
import { appendMessage, showTypingIndicator, autoResize } from './chat.js';
import { initUpload } from './upload.js';
import { initSidebar, toggleMobileSidebar } from './sidebar.js';
import { exportChatPDF } from './export.js';

// ─── Auth Guard ──────────────────────────────────────────────────────────
if (!Auth.isLoggedIn()) window.location.href = 'index.html';

// ─── State ───────────────────────────────────────────────────────────────
let activeChatId = null;
let isTyping     = false;
let modalPendingClose = null; // Track which modal is waiting for confirmation

// ─── DOM Refs ─────────────────────────────────────────────────────────────
const chatInner      = document.getElementById('chatInner');
const msgInput       = document.getElementById('msgInput');
const sendBtn        = document.getElementById('sendBtn');
const welcomeScreen  = document.getElementById('welcomeScreen');
const chatTitle      = document.getElementById('chatTitle');
const exportBtn      = document.getElementById('exportBtn');
const activeDocBadge = document.getElementById('activeDocBadge');
const activeDocName  = document.getElementById('activeDocName');
const dropZone       = document.getElementById('dropZone');
const fileInput      = document.getElementById('fileInput');
const filesPanel     = document.getElementById('filesPanel');
const inputArea      = document.querySelector('.input-area');
const chatWindow     = document.getElementById('chatWindow');

// ─── Toast helper ─────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const tc = document.getElementById('toastContainer');
  if (!tc) return;
  const t  = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  tc.appendChild(t);
  setTimeout(() => {
    t.style.transition = 'opacity 0.3s';
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
  }, 3500);
}

let isUserScrolledUp = false;

if (chatWindow) {
  chatWindow.addEventListener('scroll', () => {
    // Track if the user manually scrolled up (more than 50px from bottom)
    const distanceToBottom = chatWindow.scrollHeight - chatWindow.scrollTop - chatWindow.clientHeight;
    isUserScrolledUp = distanceToBottom > 50;
  });
}

function scrollToBottom(immediate = false) {
  if (!chatWindow) return;
  
  if (isUserScrolledUp && immediate) {
    return; // Respect user's manual scroll position during stream
  }
  
  const performScroll = () => {
    if (immediate) {
      chatWindow.scrollTop = chatWindow.scrollHeight;
    } else {
      chatWindow.scrollTo({ top: chatWindow.scrollHeight, behavior: 'smooth' });
    }
  };
  
  performScroll();
  if (!immediate) {
    // Safety fallback to ensure it snaps to bottom after smooth scroll
    setTimeout(() => chatWindow.scrollTop = chatWindow.scrollHeight, 300);
  }
}

/** 
 * Simulates a typing effect for non-streaming responses.
 */
async function typeText(bubble, text) {
  const tokens = text.split(/(\s+)/);
  let current = "";
  for (const token of tokens) {
    current += token;
    bubble.innerHTML = marked.parse(current);
    bubble.querySelectorAll('pre').forEach(block => { block.style.position = 'relative'; });
    scrollToBottom(true);
    // Fast-forward if tab is hidden
    if (!document.hidden) {
      await new Promise(r => setTimeout(r, 15 + Math.random() * 15));
    }
  }
}

// ─── User Profile Logic ──────────────────────────────────────────────────
const userBlock      = document.getElementById('userBlock');
const userMenuPopup  = document.getElementById('userMenuPopup');
const userNameText   = document.getElementById('userNameText');
const userAvatarSmall= document.getElementById('userAvatarSmall');
const menuChatsToggle= document.getElementById('menuChatsToggle');
const chatsSubmenu   = document.getElementById('chatsSubmenu');

async function loadUserProfile() {
  try {
    const profile = await UserAPI.getProfile();
    if (userNameText) userNameText.textContent = profile.name;
  } catch (err) {
    if (userNameText) userNameText.textContent = 'User';
  }
}

if (userBlock) {
  loadUserProfile();
  userBlock.addEventListener('click', (e) => {
    e.stopPropagation();
    const isShowing = userMenuPopup.classList.toggle('show');
    userBlock.classList.toggle('active', isShowing);
    
    // Always collapse chats submenu when main menu is toggled
    if (chatsSubmenu) {
      chatsSubmenu.style.display = 'none';
      const arrow = menuChatsToggle.querySelector('.submenu-arrow');
      if (arrow) arrow.classList.remove('rotated');
    }
  });

  document.addEventListener('click', () => {
    userMenuPopup.classList.remove('show');
    userBlock.classList.remove('active');
    if (chatsSubmenu) chatsSubmenu.style.display = 'none';
  });
}

const logoutBtn = document.getElementById('logoutBtn');
const logoutOverlay = document.getElementById('logoutOverlay');
const logoutCancel = document.getElementById('logoutCancel');
const logoutConfirm = document.getElementById('logoutConfirm');

if (logoutBtn && logoutOverlay) {
  logoutBtn.addEventListener('click', () => {
    logoutOverlay.classList.add('open');
  });
  
  if (logoutCancel) {
    logoutCancel.addEventListener('click', () => {
      logoutOverlay.classList.remove('open');
    });
  }
  
  if (logoutConfirm) {
    logoutConfirm.addEventListener('click', () => {
      Auth.logout();
    });
  }

  // --- About Modal Logic ---
  const menuAboutBtn = document.getElementById('menuAboutBtn');
  const aboutOverlay = document.getElementById('aboutModalOverlay');
  const closeAboutBtn = document.getElementById('closeAboutModal');

  if (menuAboutBtn && aboutOverlay) {
    menuAboutBtn.addEventListener('click', () => {
      userMenuPopup.classList.remove('show');
      aboutOverlay.classList.add('open');
    });
  }

  if (closeAboutBtn && aboutOverlay) {
    closeAboutBtn.addEventListener('click', () => {
      aboutOverlay.classList.remove('open');
    });
    aboutOverlay.addEventListener('click', (e) => {
      if (e.target === aboutOverlay) aboutOverlay.classList.remove('open');
    });
  }
}

// ─── Adaptive Layout Logic ───────────────────────────────────────────────
if (inputArea && chatWindow) {
  const updateLayout = () => {
    const height = inputArea.offsetHeight;
    // Set padding enough to clear the input area plus extra breathing room
    chatWindow.style.paddingBottom = `${height + 10}px`;
    scrollToBottom(true);
  };

  const ro = new ResizeObserver(updateLayout);
  ro.observe(inputArea);
  // Also observe window resize
  window.addEventListener('resize', updateLayout);
  updateLayout();
}
logoutOverlay.addEventListener('click', (e) => {
  if (e.target === logoutOverlay) logoutOverlay.classList.remove('open');
});

const archivedChatsBtn = document.getElementById('archivedChatsBtn');
const hiddenChatsBtn   = document.getElementById('hiddenChatsBtn');
if (archivedChatsBtn) archivedChatsBtn.addEventListener('click', () => sidebar.showFiltered('archived'));
if (hiddenChatsBtn)   hiddenChatsBtn.addEventListener('click',   () => sidebar.showFiltered('hidden'));

// ─── Profile Modal Logic ──────────────────────────────────────────────────
const menuProfileBtn      = document.getElementById('menuProfileBtn');
const profileOverlay      = document.getElementById('profileModalOverlay');
const closeProfileBtn     = document.getElementById('closeProfileModal');
const saveProfileBtn      = document.getElementById('saveProfileBtn');
const togglePasswordBtn   = document.getElementById('togglePasswordBtn');
const passwordInputs      = document.getElementById('passwordInputs');

const profileNameInput    = document.getElementById('profileNameInput');
const profileGenderSelect  = document.getElementById('profileGenderSelect');
const profileProfessionSelect = document.getElementById('profileProfessionSelect');
const profileEmailInput   = document.getElementById('profileEmailInput');

// Advanced Options
const advancedOptionsBtn = document.getElementById('advancedOptionsBtn');
const advancedMenu       = document.getElementById('advancedMenu');
const openChangePasswordBtn = document.getElementById('openChangePasswordBtn');
const openDeleteUserBtn     = document.getElementById('openDeleteUserBtn');

// Password Modal
const passwordModalOverlay = document.getElementById('passwordModalOverlay');
const currentPasswordInput = document.getElementById('currentPasswordInput');
const newPasswordInput     = document.getElementById('newPasswordInput');
const passwordCancel       = document.getElementById('passwordCancel');
const passwordConfirm      = document.getElementById('passwordConfirm');

// Delete User Modal
const deleteUserOverlay = document.getElementById('deleteUserOverlay');
const deleteUserCancel  = document.getElementById('deleteUserCancel');
const deleteUserConfirm = document.getElementById('deleteUserConfirm');

// Unsaved changes state
const unsavedOverlay = document.getElementById('unsavedChangesOverlay');
const discardChangesBtn = document.getElementById('discardChangesBtn');
const saveAndCloseBtn = document.getElementById('saveAndCloseBtn');

let initialProfileState = { name: '', gender: '', profession: '' };

function getProfileCurrentState() {
  return {
    name: profileNameInput.value.trim(),
    gender: profileGenderSelect.value,
    profession: profileProfessionSelect.value
  };
}

function hasProfileChanges() {
  const current = getProfileCurrentState();
  // Simplified since password is now in its own modal
  return current.name !== initialProfileState.name || 
         current.gender !== initialProfileState.gender || 
         current.profession !== initialProfileState.profession;
}

// Custom Select Implementation
function setupCustomSelect(containerId, triggerId, valueSpanId, optionsId, inputId) {
  const container = document.getElementById(containerId);
  const trigger = document.getElementById(triggerId);
  const valueSpan = document.getElementById(valueSpanId);
  const options = document.getElementById(optionsId);
  const hiddenInput = document.getElementById(inputId);

  if (!trigger || !options) return;

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    // Close other selects
    document.querySelectorAll('.custom-select-options').forEach(opt => {
      if (opt !== options) opt.classList.remove('show');
    });
    options.classList.toggle('show');
  });

  options.querySelectorAll('.custom-option').forEach(option => {
    option.addEventListener('click', () => {
      const val = option.getAttribute('data-value');
      const text = option.textContent;
      valueSpan.textContent = text;
      hiddenInput.value = val;
      options.classList.remove('show');
    });
  });

  // Helper to set value programmatically
  return {
    setValue: (val) => {
      hiddenInput.value = val;
      const option = options.querySelector(`[data-value="${val}"]`);
      valueSpan.textContent = option ? option.textContent : `Select ${inputId.includes('Gender') ? 'Gender' : 'Profession'}`;
    }
  };
}

const genderSelect = setupCustomSelect('genderSelectContainer', 'genderSelectTrigger', 'genderSelectValue', 'genderOptions', 'profileGenderSelect');
const professionSelect = setupCustomSelect('professionSelectContainer', 'professionSelectTrigger', 'professionSelectValue', 'professionOptions', 'profileProfessionSelect');
const themeSelectCustom = setupCustomSelect('themeSelectContainer', 'themeSelectTrigger', 'themeSelectValue', 'themeOptions', 'themeSelectDropdown');
const summarySelectCustom = setupCustomSelect('summarySelectContainer', 'summarySelectTrigger', 'summarySelectValue', 'summaryOptions', 'defaultSummarySelect');

// Close selects on outside click
document.addEventListener('click', () => {
  document.querySelectorAll('.custom-select-options').forEach(opt => opt.classList.remove('show'));
});

if (menuProfileBtn) {
  menuProfileBtn.addEventListener('click', async () => {
    try {
      const profile = await UserAPI.getProfile();
      initialProfileState = { 
        name: profile.name || '', 
        gender: profile.gender || '', 
        profession: profile.profession || '' 
      };
      
      if (profileNameInput)   profileNameInput.value   = initialProfileState.name;
      if (genderSelect)        genderSelect.setValue(initialProfileState.gender);
      if (professionSelect)    professionSelect.setValue(initialProfileState.profession);
      if (profileEmailInput)  profileEmailInput.value  = profile.email || '';
      
      // Reset advanced section
      if (advancedMenu) advancedMenu.style.display = 'none';
      
      profileOverlay.classList.add('open');
    } catch (err) {
      showToast('Failed to load profile', 'error');
    }
  });
}

// Advanced Options Toggle
if (advancedOptionsBtn && advancedMenu) {
  advancedOptionsBtn.addEventListener('click', () => {
    const isHidden = advancedMenu.style.display === 'none';
    advancedMenu.style.display = isHidden ? 'flex' : 'none';
    advancedOptionsBtn.querySelector('svg').style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0)';
  });
}

// Password Flow
if (openChangePasswordBtn) {
  openChangePasswordBtn.addEventListener('click', () => {
    passwordModalOverlay.classList.add('open');
    if (currentPasswordInput) currentPasswordInput.value = '';
    if (newPasswordInput)     newPasswordInput.value = '';
  });
}

if (passwordCancel) passwordCancel.addEventListener('click', () => passwordModalOverlay.classList.remove('open'));
if (passwordConfirm) {
  passwordConfirm.addEventListener('click', async () => {
    const current_password = currentPasswordInput.value;
    const new_password     = newPasswordInput.value;
    if (!current_password || !new_password) {
      return showToast('Both fields are required', 'warning');
    }
    try {
      await UserAPI.patchProfile({ current_password, new_password });
      showToast('Password updated', 'success');
      passwordModalOverlay.classList.remove('open');
    } catch (err) {
      showToast(err.message || 'Failed to update password', 'error');
    }
  });
}

// Delete User Flow
if (openDeleteUserBtn) {
  openDeleteUserBtn.addEventListener('click', () => deleteUserOverlay.classList.add('open'));
}
if (deleteUserCancel) deleteUserCancel.addEventListener('click', () => deleteUserOverlay.classList.remove('open'));
if (deleteUserConfirm) {
  deleteUserConfirm.addEventListener('click', async () => {
    try {
      await UserAPI.deleteUser(); // We need to add this to api.js
      showToast('Account deleted', 'info');
      Auth.logout();
    } catch (err) {
      showToast('Failed to delete account', 'error');
    }
  });
}

function closeProfileSafely() {
  if (hasProfileChanges()) {
    modalPendingClose = 'profile';
    unsavedOverlay.classList.add('open');
  } else {
    profileOverlay.classList.remove('open');
  }
}

if (closeProfileBtn) {
  closeProfileBtn.addEventListener('click', closeProfileSafely);
}

if (discardChangesBtn) {
  discardChangesBtn.addEventListener('click', () => {
    unsavedOverlay.classList.remove('open');
    if (modalPendingClose === 'profile') {
      profileOverlay.classList.remove('open');
    } else if (modalPendingClose === 'personalization') {
      personalizationOverlay.classList.remove('open');
    }
    modalPendingClose = null;
    showToast('Changes discarded', 'info');
  });
}

if (saveAndCloseBtn) {
  saveAndCloseBtn.addEventListener('click', async () => {
    unsavedOverlay.classList.remove('open');
    let msg = 'Changes saved';
    if (modalPendingClose === 'profile') {
      await saveProfile();
    } else if (modalPendingClose === 'personalization') {
      await savePersonalization();
      msg = 'Preferences saved successfully';
    }
    modalPendingClose = null;
    showToast(msg, 'success');
  });
}

// Removed old password toggle logic

async function saveProfile() {
  const { name, gender, profession } = getProfileCurrentState();
  const body = { name, gender, profession };
  
  try {
    await UserAPI.patchProfile(body);
    profileOverlay.classList.remove('open');
    loadUserProfile(); // Refresh name on badge
    return true;
  } catch (err) {
    showToast(err.message || 'Failed to update profile', 'error');
    throw err;
  }
}

if (saveProfileBtn) {
  saveProfileBtn.addEventListener('click', async () => {
    try {
      await saveProfile();
      showToast('Profile updated successfully!', 'success');
    } catch (err) { /* Toast already shown in saveProfile */ }
  });
}

// ─── Personalization Modal Logic ──────────────────────────────────────────
const menuPersonalizationBtn   = document.getElementById('menuPersonalizationBtn');
const personalizationOverlay   = document.getElementById('personalizationModalOverlay');
const closePersonalizationBtn  = document.getElementById('closePersonalizationModal');
const savePersonalizationBtn   = document.getElementById('savePersonalizationBtn');
const languageLockBtn          = document.getElementById('languageLockBtn');
const themeSelectDropdown      = document.getElementById('themeSelectDropdown');
const defaultSummarySelect     = document.getElementById('defaultSummarySelect');
const autoDetectToggle         = document.getElementById('autoDetectToggle');
const privacyDeleteToggle      = document.getElementById('privacyDeleteToggle');

if (menuPersonalizationBtn) {
  menuPersonalizationBtn.addEventListener('click', () => {
    personalizationOverlay.classList.add('open');
    // Load current values
    const currentTheme = localStorage.getItem('docuchat_theme') || 'dark';
    if (themeSelectCustom) {
      themeSelectCustom.setValue(currentTheme);
    } else if (themeSelectDropdown) {
      themeSelectDropdown.value = currentTheme;
    }
    
    const savedSummary = localStorage.getItem('docuchat_summary_length') || 'detailed';
    if (summarySelectCustom) {
      summarySelectCustom.setValue(savedSummary);
    } else if (defaultSummarySelect) {
      defaultSummarySelect.value = savedSummary;
    }
    
    const autoDetect = localStorage.getItem('docuchat_auto_detect') !== 'false';
    if (autoDetectToggle) autoDetectToggle.checked = autoDetect;
    
    const privacyDelete = localStorage.getItem('docuchat_privacy_delete') === 'true';
    if (privacyDeleteToggle) privacyDeleteToggle.checked = privacyDelete;
  });
}

// Handled in personalization modal logic block below

if (languageLockBtn) {
  languageLockBtn.addEventListener('click', () => {
    showToast('More languages will come soon!', 'info');
  });
}

function getPersonalizationCurrentState() {
  return {
    theme: themeSelectDropdown.value,
    summary: defaultSummarySelect.value,
    autoDetect: autoDetectToggle.checked,
    privacyDelete: privacyDeleteToggle.checked
  };
}

function hasPersonalizationChanges() {
  const current = getPersonalizationCurrentState();
  const savedTheme = localStorage.getItem('docuchat_theme') || 'dark';
  const savedSummary = localStorage.getItem('docuchat_summary_length') || 'detailed';
  const savedAutoDetect = localStorage.getItem('docuchat_auto_detect') !== 'false';
  const savedPrivacyDelete = localStorage.getItem('docuchat_privacy_delete') === 'true';

  return (
    current.theme !== savedTheme ||
    current.summary !== savedSummary ||
    current.autoDetect !== savedAutoDetect ||
    current.privacyDelete !== savedPrivacyDelete
  );
}

async function savePersonalization() {
  const current = getPersonalizationCurrentState();
  localStorage.setItem('docuchat_theme', current.theme);
  localStorage.setItem('docuchat_summary_length', current.summary);
  localStorage.setItem('docuchat_auto_detect', current.autoDetect);
  localStorage.setItem('docuchat_privacy_delete', current.privacyDelete);

  document.documentElement.setAttribute('data-theme', current.theme);
  
  try {
    await UserAPI.updatePreferences({
      theme:            current.theme,
      summary_mode:     current.summary,
      auto_delete_docs: current.privacyDelete
    });
  } catch (err) {
    showToast('Failed to save preferences to backend', 'error');
  }

  personalizationOverlay.classList.remove('open');
  return true;
}

if (savePersonalizationBtn) {
  savePersonalizationBtn.addEventListener('click', async () => {
    await savePersonalization();
    showToast('Preferences applied successfully!', 'success');
  });
}

if (closePersonalizationBtn) {
  closePersonalizationBtn.addEventListener('click', () => {
    if (hasPersonalizationChanges()) {
      modalPendingClose = 'personalization';
      unsavedOverlay.classList.add('open');
    } else {
      personalizationOverlay.classList.remove('open');
    }
  });
}

// ─── Sidebar (chat history) ───────────────────────────────────────────────
const sidebar = initSidebar({
  listEl:          document.getElementById('chatHistoryList'),
  searchInput:     document.getElementById('chatSearchInput'),
  getActiveChatId: () => activeChatId,
  showToast,
  onChatSelect:    (id, title) => {
    if (document.body.classList.contains('selection-mode')) {
      showToast('Please select the messages in this chat or cancel selection mode first.', 'warning');
      return false;
    }
    loadChat(id, title);
  },
  onChatDelete:    (id)        => { if (activeChatId === id) resetChatView(); },
});

// ─── Upload controller ────────────────────────────────────────────────────
const uploader = initUpload({
  dropZone, fileInput, filesPanel, activeDocBadge, activeDocName, showToast,
  onUpload: (result) => console.log('File uploaded:', result.original_name),
  getActiveChatId: () => activeChatId,
  onNewChatCreated: async (chat) => {
    activeChatId = chat.id;
    chatTitle.textContent = 'New Chat';
    exportBtn.style.display = 'flex';
    welcomeScreen.style.display = 'flex';
    sidebar.setActive(activeChatId);
    await sidebar.refresh();
  }
});
// uploader.restore() is no longer needed here as loadChat handles it per-chat

// ─── Load a chat (open from sidebar) ──────────────────────────────────────
const chatDrafts = {};

async function loadChat(chatId, title) {
  // Save current draft before switching
  if (activeChatId) {
    chatDrafts[activeChatId] = msgInput.value;
  }

  activeChatId = chatId;
  chatTitle.textContent = title || 'Chat';
  
  // Restore draft for new chat
  msgInput.value = chatDrafts[chatId] || '';
  autoResize(msgInput);
  
  // Persist for reload
  localStorage.setItem('activeChatId', chatId);
  localStorage.setItem('activeChatTitle', title || 'Chat');
  
  exportBtn.style.display = 'flex';
  document.documentElement.style.removeProperty('--welcome-display');
  welcomeScreen.style.display = 'none';
  document.querySelectorAll('.message').forEach(m => m.remove());
  sidebar.setActive(chatId);

  try {
    const data = await ChatAPI.getChat(chatId);
    data.messages.forEach(m => appendMessage(chatInner, m.role, m.content));
    
    if (data.messages.length === 0) {
      welcomeScreen.style.display = 'flex';
    }
    scrollToBottom();
  } catch (err) {
    showToast('Failed to load chat.', 'error');
    resetChatView();
  }

  // Load documents for this specific chat
  const lastFileId = localStorage.getItem(`activeFile_${chatId}`);
  await uploader.loadFilesForChat(chatId);
  
  if (lastFileId) {
    // Attempt to re-select the last active file for this chat
    // We search the DOM again because loadFilesForChat just re-rendered it
    const card = document.querySelector(`.doc-card[data-id="${lastFileId}"]`);
    if (card) {
      card.click();
    }
  } else {
    uploader.deselect();
  }
}

// ─── New Chat button ──────────────────────────────────────────────────────
const newChatBtn = document.getElementById('newChatBtn');
if (newChatBtn) {
  newChatBtn.addEventListener('click', async () => {
    try {
      const chat = await ChatAPI.newChat();
      activeChatId = chat.id;
      chatTitle.textContent = 'New Chat';
      exportBtn.style.display = 'flex';
      document.querySelectorAll('.message').forEach(m => m.remove());
      welcomeScreen.style.display = 'flex';
      sidebar.setActive(chat.id);
      await sidebar.refresh();
      
      uploader.deselect();
      await uploader.loadFilesForChat(chat.id);
    } catch (err) {
      showToast('Failed to create chat.', 'error');
    }
  });
}

// ─── Send message ─────────────────────────────────────────────────────────
async function sendMessage() {
  const content = msgInput.value.trim();
  if (!content || isTyping) return;

  // 1. Initial State & UI Feedback
  isTyping = true;
  sendBtn.disabled = true;
  msgInput.value = ''; // Clear immediately to prevent double-submit
  if (activeChatId) delete chatDrafts[activeChatId];
  autoResize(msgInput);

  // 2. Chat Persistence (Create if new)
  if (!activeChatId) {
    try {
      const chat = await ChatAPI.newChat();
      activeChatId = chat.id;
      if (exportBtn) exportBtn.style.display = 'flex';
      welcomeScreen.style.display = 'none';
      if (window.sidebar) {
        sidebar.setActive(activeChatId);
        await sidebar.refresh();
      }
    } catch (err) {
      showToast('Failed to create chat.', 'error');
      msgInput.value = content; 
      isTyping = false;
      sendBtn.disabled = false;
      return;
    }
  }

  const language = document.getElementById('languageSelect').value;
  const fileId = uploader.getActiveFileId();

  // 3. Summary Mode Detection
  const summaryPrompts = {
    detailed: "Give the detailed summary of the document",
    short: "Provide a short summary of the document",
    bullet: "Summarize this document in bullet points",
    executive: "Generate an executive summary of this document",
    study_notes: "Create detailed study notes from this document",
    key_insights: "What are the main conclusions?",
    action_items: "Give me action items from this document",
    explain_simply: "Explain this document in simple terms"
  };
  const summaryModeSelect = document.getElementById('summaryModeSelect');
  const currentMode = summaryModeSelect ? summaryModeSelect.value : null;
  let summaryMode = (currentMode && content === summaryPrompts[currentMode]) ? currentMode : null;
  
  if (!summaryMode) {
    for (const [mode, prompt] of Object.entries(summaryPrompts)) {
      if (content === prompt) { summaryMode = mode; break; }
    }
  }

  // 4. UI Preparation
  welcomeScreen.style.display = 'none';
  appendMessage(chatInner, 'user', content);
  scrollToBottom();
  
  // Refresh sidebar immediately for new chats so the title appears right away
  await sidebar.refresh();
  sidebar.setActive(activeChatId);

  const typingEl = showTypingIndicator(chatInner);

  try {
    if (summaryMode) {
      // Use non-streaming API for Map-Reduce tasks (background processing)
      const resp = await ChatAPI.sendMessage(activeChatId, content, fileId, language, summaryMode);
      if (typingEl) typingEl.remove();
      
      const assistantContent = resp.assistant_message.content;
      const msgId = resp.assistant_message.id;

      if (assistantContent === '[SYNTHESIZING]') {
        appendMessage(chatInner, 'assistant', assistantContent, msgId);
        pollSummary(activeChatId, msgId);
      } else {
        const messageEl = appendMessage(chatInner, 'assistant', '', msgId);
        const bubble = messageEl.querySelector('.msg-bubble');
        await typeText(bubble, assistantContent);
      }
    } else {
      // Use streaming API for regular chat with a controlled typing speed
      if (typingEl) typingEl.remove();
      const messageEl = appendMessage(chatInner, 'assistant', '', null);
      const bubble = messageEl.querySelector('.msg-bubble');
      
      let fullText = "";
      let tokenQueue = [];
      let streamFinished = false;

      // Producer: Consume the stream as fast as it comes
      const streamPromise = ChatAPI.sendMessageStream(activeChatId, content, fileId, language, (token) => {
        tokenQueue.push(token);
      }).then(() => { streamFinished = true; }).catch(err => { streamFinished = true; throw err; });

      // Consumer: Render tokens at a controlled "writing style" speed
      while (!streamFinished || tokenQueue.length > 0) {
        if (tokenQueue.length > 0) {
          const token = tokenQueue.shift();
          fullText += token;
          bubble.innerHTML = marked.parse(fullText);
          bubble.querySelectorAll('pre').forEach(block => { block.style.position = 'relative'; });
          scrollToBottom(true);
          
          // Match the comfortable speed of document summaries, but fast-forward if hidden
          if (!document.hidden) {
            await new Promise(r => setTimeout(r, 20));
          }
        } else {
          // Brief pause to wait for next chunk
          if (!document.hidden) {
            await new Promise(r => setTimeout(r, 10));
          }
        }
      }
      
      await streamPromise; 
      
      // Update sidebar and title immediately after stream finishes
      await sidebar.refresh();
      sidebar.setActive(activeChatId);
      const updatedChat = await ChatAPI.getChat(activeChatId);
      if (updatedChat && updatedChat.title) {
        chatTitle.textContent = updatedChat.title;
      }
    }

    // After completion, update UI state
    await sidebar.refresh();
    sidebar.setActive(activeChatId);
    
    // Explicitly update the topbar title from the DB
    try {
      const chatData = await ChatAPI.getChat(activeChatId);
      if (chatTitle) chatTitle.textContent = chatData.title;
    } catch (e) {
      console.error("Failed to update chat header:", e);
    }
  } catch (err) {
    if (typingEl) typingEl.remove();
    showToast(err.message || 'Failed to send message.', 'error');
  } finally {
    isTyping = false;
    sendBtn.disabled = false;
    scrollToBottom();
  }
}

if (sendBtn) {
  sendBtn.addEventListener('click', sendMessage);
  msgInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  msgInput.addEventListener('input', () => {
    autoResize(msgInput);
    sendBtn.disabled = !msgInput.value.trim();
    // Save draft
    if (activeChatId) {
      chatDrafts[activeChatId] = msgInput.value;
    }
  });
}

// ─── Suggestion cards ─────────────────────────────────────────────────────
document.querySelectorAll('.suggestion-card').forEach(card => {
  card.addEventListener('click', () => {
    msgInput.value = card.dataset.prompt;
    msgInput.dispatchEvent(new Event('input'));
    msgInput.focus();
    
    // Auto-send if a document is selected
    if (uploader.getActiveFileId()) {
      sendMessage();
    }
  });
});

// ─── Upload button ────────────────────────────────────────────────────────
const uploadTriggerBtn = document.getElementById('uploadTriggerBtn');
const attachMenu = document.getElementById('attachMenu');

if (uploadTriggerBtn && attachMenu) {
  uploadTriggerBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    const icon = uploadTriggerBtn.querySelector('.plus-icon');
    const optionsBar = document.querySelector('.options-bar');
    if (icon) icon.classList.toggle('rotated');
    
    const optionsBarNowShifted = optionsBar && optionsBar.classList.contains('shifted');
    
    if (optionsBar && !optionsBarNowShifted) {
      optionsBar.classList.add('shifted');
      // Delay the menu pop to allow movement to start
      setTimeout(() => {
        attachMenu.classList.add('show');
      }, 150);
    } else if (optionsBar) {
      attachMenu.classList.remove('show');
      setTimeout(() => {
        optionsBar.classList.remove('shifted');
      }, 100);
    }
  });

  document.addEventListener('click', (e) => {
    if (!attachMenu.contains(e.target) && !uploadTriggerBtn.contains(e.target)) {
      attachMenu.classList.remove('show');
      const optionsBar = document.querySelector('.options-bar');
      if (optionsBar) {
        setTimeout(() => {
          optionsBar.classList.remove('shifted');
        }, 100);
      }
      const icon = uploadTriggerBtn.querySelector('.plus-icon');
      if (icon) icon.classList.remove('rotated');
    }
  });

  attachMenu.querySelectorAll('.attach-item').forEach(item => {
    item.addEventListener('click', () => {
      const type = item.getAttribute('data-type');
      if (type) {
        fileInput.setAttribute('accept', type);
        fileInput.click();
      }
      attachMenu.classList.remove('show');
      const optionsBar = document.querySelector('.options-bar');
      if (optionsBar) optionsBar.classList.remove('shifted');
      const icon = uploadTriggerBtn.querySelector('.plus-icon');
      if (icon) icon.classList.remove('rotated');
    });
  });
}

// ─── Custom Dropdowns ─────────────────────────────────────────────────────
document.querySelectorAll('.custom-dropdown').forEach(dropdown => {
  const selected = dropdown.querySelector('.dropdown-selected');
  const textSpan = dropdown.querySelector('.sel-text');
  const input = dropdown.querySelector('input[type="hidden"]');
  const options = dropdown.querySelectorAll('.dropdown-item');

  selected.addEventListener('click', (e) => {
    e.stopPropagation();
    document.querySelectorAll('.custom-dropdown.open').forEach(d => {
      if (d !== dropdown) d.classList.remove('open');
    });
    dropdown.classList.toggle('open');
  });

  options.forEach(opt => {
    opt.addEventListener('click', () => {
      const val = opt.getAttribute('data-value');
      input.value = val;
      textSpan.textContent = opt.textContent;
      dropdown.classList.remove('open');

      // Auto-fill prompt for summary dropdown
      if (dropdown.id === 'summaryDropdown') {
        const msgInput = document.getElementById('msgInput');
        const prompts = {
          detailed: "Give the detailed summary of the document",
          short: "Provide a short summary of the document",
          bullet: "Summarize this document in bullet points",
          executive: "Generate an executive summary of this document",
          study_notes: "Create detailed study notes from this document"
        };
        if (prompts[val]) {
          msgInput.value = prompts[val];
          // Trigger auto-resize if imported/available
          msgInput.dispatchEvent(new Event('input'));
        }
      }
    });
  });
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.custom-dropdown')) {
    document.querySelectorAll('.custom-dropdown.open').forEach(d => d.classList.remove('open'));
  }
});

// ─── Export PDF ───────────────────────────────────────────────────────────
if (exportBtn) {
  exportBtn.addEventListener('click', () => {
    const exportOverlay = document.getElementById('exportOverlay');
    const exportFilenameInput = document.getElementById('exportFilename');
    const scopeSelect = document.getElementById('scopeSelect');
    const scopeDropdownText = document.querySelector('#scopeDropdown .sel-text');

    if (exportOverlay) exportOverlay.classList.add('open');
    if (exportFilenameInput) {
      exportFilenameInput.value = chatTitle.textContent || 'Exported Chat';
      exportFilenameInput.select(); // Highlight the text for easy editing
    }
    // Always default to 'Entire Chat' when opening the modal
    if (scopeSelect) scopeSelect.value = 'entire';
    if (scopeDropdownText) scopeDropdownText.textContent = 'Entire Chat';
  });
}

// Scope Toggle Logic no longer needed as it's handled by generic dropdown logic in JS
// We just need to read the hidden input value in the exportConfirm listener.

const exportCancel  = document.getElementById('exportCancel');
const exportConfirm = document.getElementById('exportConfirm');
const exportOverlay = document.getElementById('exportOverlay');

if (exportCancel && exportOverlay) {
  exportCancel.addEventListener('click', () => exportOverlay.classList.remove('open'));
}

let selectionModeActive = false;
let selectedMessages = [];

if (exportConfirm && exportOverlay) {
  exportConfirm.addEventListener('click', async () => {
    const filename = document.getElementById('exportFilename').value;
    const scopeSelect = document.getElementById('scopeSelect');
    const currentExportScope = scopeSelect ? scopeSelect.value : 'entire';
    
    if (currentExportScope === 'entire') {
      exportOverlay.classList.remove('open');
      await exportChatPDF(activeChatId, showToast, null, filename);
    } else {
      // Start Selective Mode
      exportOverlay.classList.remove('open');
      selectionModeActive = true;
      selectedMessages = [];
      selectedCount.textContent = '0';
      document.body.classList.add('selection-mode');
      selectionToolbar.style.display = 'flex';
      showToast('Click messages to select them', 'info');
    }
  });
}

const selectionToolbar = document.getElementById('selectionToolbar');
const cancelSelectionBtn = document.getElementById('cancelSelectionBtn');
const confirmSelectionExportBtn = document.getElementById('confirmSelectionExportBtn');
const selectedCount = document.getElementById('selectedCount');

if (cancelSelectionBtn) {
  cancelSelectionBtn.addEventListener('click', () => {
    selectionModeActive = false;
    document.body.classList.remove('selection-mode');
    selectionToolbar.style.display = 'none';
    document.querySelectorAll('.message.selected').forEach(m => m.classList.remove('selected'));
  });
}

if (confirmSelectionExportBtn) {
  confirmSelectionExportBtn.addEventListener('click', async () => {
    if (selectedMessages.length === 0) {
      showToast('Select at least one message', 'warning');
      return;
    }
    const filename = document.getElementById('exportFilename').value;
    await exportChatPDF(activeChatId, showToast, selectedMessages, filename);
    
    // Exit selection mode
    selectionModeActive = false;
    document.body.classList.remove('selection-mode');
    selectionToolbar.style.display = 'none';
    document.querySelectorAll('.message.selected').forEach(m => m.classList.remove('selected'));
  });
}

// Handle message selection click
if (chatInner) {
  chatInner.addEventListener('click', (e) => {
    if (!selectionModeActive) return;
    
    const messageEl = e.target.closest('.message');
    if (!messageEl) return;
    
    const role = messageEl.classList.contains('user') ? 'user' : 'assistant';
    const content = messageEl.querySelector('.msg-bubble').innerText;
    
    const msgObj = { role, content };
    const index = selectedMessages.findIndex(m => m.content === content && m.role === role);
    
    if (index > -1) {
      selectedMessages.splice(index, 1);
      messageEl.classList.remove('selected');
    } else {
      selectedMessages.push(msgObj);
      messageEl.classList.add('selected');
    }
    
    selectedCount.textContent = selectedMessages.length;
  });
}

// ─── Settings modal ───────────────────────────────────────────────────────
const settingsBtn = document.getElementById('settingsBtn');
const closeSettingsBtn = document.getElementById('closeSettingsBtn');
const settingsOverlay = document.getElementById('settingsOverlay');
const themeSelect = document.getElementById('themeSelect');

if (settingsBtn) {
  settingsBtn.addEventListener('click', () => settingsOverlay.classList.add('open'));
}
if (closeSettingsBtn) {
  closeSettingsBtn.addEventListener('click', () => settingsOverlay.classList.remove('open'));
}
if (settingsOverlay) {
  settingsOverlay.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('open');
  });
}
if (themeSelect) {
  themeSelect.addEventListener('change', (e) => {
    document.documentElement.setAttribute('data-theme', e.target.value);
    localStorage.setItem('docuchat_theme', e.target.value);
  });
}

// ─── Mobile sidebar toggle ────────────────────────────────────────────────
const sidebarEl     = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
if (window.innerWidth <= 768 && sidebarToggle) sidebarToggle.style.display = 'flex';
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => toggleMobileSidebar(sidebarEl));
}

// ─── Submenu Toggle ───────────────────────────────────────────────────────
if (menuChatsToggle && chatsSubmenu) {
  menuChatsToggle.addEventListener('click', (e) => {
    e.stopPropagation();
    const isHidden = chatsSubmenu.style.display === 'none';
    chatsSubmenu.style.display = isHidden ? 'flex' : 'none';
    const arrow = menuChatsToggle.querySelector('.submenu-arrow');
    if (arrow) arrow.classList.toggle('rotated', isHidden);
  });
}

// ─── Polling for long summaries ──────────────────────────────────────────
async function pollSummary(chatId, messageId) {
  const MAX_POLLS = 240; // Stop after 20 minutes (240 × 5s)
  let pollCount = 0;

  const pollInterval = setInterval(async () => {
    pollCount++;
    if (pollCount > MAX_POLLS || activeChatId !== chatId) {
      clearInterval(pollInterval);
      return;
    }

    try {
      const data = await ChatAPI.getChat(chatId);
      const msg = data.messages.find(m => m.id === messageId);
      
      if (msg && msg.content !== '[SYNTHESIZING]') {
        clearInterval(pollInterval);
        
        // Refresh sidebar and title because the background task may have generated a new title based on the response
        await sidebar.refresh();
        if (data && data.title && data.title !== 'New Chat') {
          chatTitle.textContent = data.title;
        }

        // Find this specific message bubble by its data-message-id tag
        const targetEl = document.querySelector(`[data-message-id="${messageId}"]`);
        if (targetEl) {
          const bubble = targetEl.querySelector('.msg-bubble');
          if (bubble) {
            bubble.innerHTML = ''; // Clear SYNTHESIZING
            await typeText(bubble, msg.content);
          }
        }
        
        showToast('Summary ready!', 'success');
      }
    } catch (err) {
      console.error('Polling failed:', err);
    }
  }, 5000);
}


// ─── Reset chat view ──────────────────────────────────────────────────────
function resetChatView() {
  activeChatId = null;
  chatTitle.textContent = '';
  localStorage.removeItem('activeChatId');
  localStorage.removeItem('activeChatTitle');
  exportBtn.style.display = 'none';
  document.querySelectorAll('.message').forEach(m => m.remove());
  document.documentElement.style.removeProperty('--welcome-display');
  welcomeScreen.style.display = 'flex';
  filesPanel.innerHTML = '<div style="color:var(--text-muted);font-size:13px;padding:8px 12px;">Select a chat to see its documents.</div>';
  if (msgInput) {
    msgInput.value = '';
  }
}

// ─── Init: restore theme ──────────────────────────────────────────────────
const savedTheme = localStorage.getItem('docuchat_theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);
if (themeSelect) themeSelect.value = savedTheme;
// Restore session on load
window.addEventListener('DOMContentLoaded', () => {
  const savedId = localStorage.getItem('activeChatId');
  const savedTitle = localStorage.getItem('activeChatTitle');
  if (savedId && savedTitle) {
    // Attempt to load multiple times if needed to ensure history is ready
    let attempts = 0;
    const restore = setInterval(() => {
      const item = document.getElementById(`chat-item-${savedId}`);
      if (item || attempts > 10) {
        loadChat(parseInt(savedId), savedTitle);
        if (sidebar && sidebar.setActive) sidebar.setActive(parseInt(savedId));
        clearInterval(restore);
      }
      attempts++;
    }, 200);
  }
});
