/**
 * frontend/js/chat.js — Chat message rendering utilities.
 *
 * Exports:
 *   appendMessage(container, role, content) → HTMLElement
 *   showTypingIndicator(container) → HTMLElement
 *   autoResize(textarea)
 */

/**
 * Create and append a chat message bubble to the container.
 *
 * @param {HTMLElement} container - The #chatInner element.
 * @param {'user'|'assistant'} role
 * @param {string} content
 * @returns {HTMLElement} The created message element.
 */
export function appendMessage(container, role, content) {
  const wrap   = document.createElement('div');
  wrap.className = `message ${role}`;


  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  
  if (role === 'assistant') {
    // Render markdown for assistant
    bubble.innerHTML = marked.parse(content);
  } else {
    bubble.textContent = content;
  }

  wrap.appendChild(bubble);
  container.appendChild(wrap);

  // Scroll to bottom
  wrap.scrollIntoView({ behavior: 'smooth', block: 'end' });

  return wrap;
}

/**
 * Show the three-dot typing indicator while waiting for the AI.
 *
 * @param {HTMLElement} container
 * @returns {HTMLElement} The typing element (call .remove() when done).
 */
export function showTypingIndicator(container) {
  const wrap = document.createElement('div');
  wrap.className = 'message assistant typing-indicator';



  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement('div');
    dot.className = 'typing-dot';
    bubble.appendChild(dot);
  }
  wrap.appendChild(bubble);
  container.appendChild(wrap);
  wrap.scrollIntoView({ behavior: 'smooth', block: 'end' });

  return wrap;
}

/**
 * Auto-resize a textarea to fit its content (up to its max-height).
 *
 * @param {HTMLTextAreaElement} textarea
 */
export function autoResize(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${textarea.scrollHeight}px`;
}
