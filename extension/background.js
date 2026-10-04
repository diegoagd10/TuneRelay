// Hands the active tab's URL to the TuneRelay native host. The host owns
// URL validation, de-duplication, the download and every notification.
const HOST = 'com.tunerelay.host';

function sendUrl(url) {
  if (!url || !/^https?:/i.test(url)) return;
  chrome.runtime.sendNativeMessage(HOST, { url }, () => {
    void chrome.runtime.lastError;
  });
}

function capture(tab) {
  if (!tab) return;

  // activeTab exposes tab.url when the user invokes the extension
  // (toolbar click or keyboard shortcut).
  if (tab.url) {
    sendUrl(tab.url);
    return;
  }

  // Fallback: read the URL straight from the page.
  if (tab.id === undefined) return;
  chrome.scripting
    .executeScript({ target: { tabId: tab.id }, func: () => location.href })
    .then((results) => sendUrl(results && results[0] && results[0].result))
    .catch(() => {});
}

// Keyboard shortcut (Alt+Shift+M).
chrome.commands.onCommand.addListener((command) => {
  if (command === 'capture') {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => capture(tabs[0]));
  }
});

// Toolbar icon.
chrome.action.onClicked.addListener((tab) => capture(tab));
