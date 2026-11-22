export default function NotificationSettings() {
  return (
    <main>
      <h1>Settings</h1>
      <input type="checkbox" id="email-news" />
      <label htmlFor="email-news">News and updates</label>
      <input type="checkbox" id="email-mentions" />
      <label htmlFor="email-mentions">Mentions</label>
      <input type="checkbox" id="email-digest" />
      <label htmlFor="email-digest">Daily digest</label>
      <input type="checkbox" id="email-receipts" />
      <label htmlFor="email-receipts">Receipts</label>
      <input type="checkbox" id="push-alerts" />
      <label htmlFor="push-alerts">Push alerts</label>
      <input type="checkbox" id="push-sound" />
      <label htmlFor="push-sound">Sound on push</label>
      <input type="checkbox" id="push-preview" />
      <label htmlFor="push-preview">Message preview</label>
      <input type="checkbox" id="sms-critical" />
      <label htmlFor="sms-critical">Critical alerts by text</label>
      <input type="checkbox" id="sms-marketing" />
      <label htmlFor="sms-marketing">Offers by text</label>
      <input type="checkbox" id="desktop-banner" />
      <label htmlFor="desktop-banner">Desktop banner</label>
      <input type="checkbox" id="desktop-badge" />
      <label htmlFor="desktop-badge">Taskbar badge</label>
      <input type="checkbox" id="mobile-vibrate" />
      <label htmlFor="mobile-vibrate">Vibrate on mobile</label>
      <input type="checkbox" id="weekly-report" />
      <label htmlFor="weekly-report">Weekly summary</label>
      <input type="checkbox" id="auto-archive" />
      <label htmlFor="auto-archive">Archive read items</label>
      <input type="checkbox" id="sync-status" />
      <label htmlFor="sync-status">Sync status banner</label>
      <input type="checkbox" id="beta-flags" />
      <label htmlFor="beta-flags">Beta feature notes</label>
      <input type="text" placeholder="Quiet hours start" />
      <input type="text" placeholder="Quiet hours end" />
      <button>Save preferences</button>
    </main>
  );
}
