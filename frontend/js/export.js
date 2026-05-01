/**
 * frontend/js/export.js — PDF export handler.
 *
 * Calls the /export/pdf endpoint and triggers a browser download.
 *
 * Usage:
 *   import { exportChatPDF } from './export.js';
 *   exportChatPDF(chatId, showToast);
 */

import { ExportAPI } from './api.js';

/**
 * Export the given chat as a PDF and trigger a file download.
 *
 * @param {number|null} chatId
 * @param {Function} showToast - showToast(message, type) function
 */
export async function exportChatPDF(chatId, showToast) {
  if (!chatId) {
    showToast('No active chat to export', 'warning');
    return;
  }

  showToast('Generating PDF…', 'info');

  try {
    const blob = await ExportAPI.exportPDF(chatId);

    // Trigger download
    const url  = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href     = url;
    link.download = `docuchat_${chatId}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    showToast('✅ PDF downloaded!', 'success');
  } catch (err) {
    showToast(`Export failed: ${err.message}`, 'error');
  }
}
