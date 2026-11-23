export default function ShareDialog() {
  return (
    <div>
      <h2>Share this report</h2>
      <p>Anyone with the link can view the contents.</p>
      <label>
        Email address
        <input type="email" placeholder="name@example.com" />
      </label>
      <label>
        Role
        <select>
          <option>Viewer</option>
          <option>Editor</option>
        </select>
      </label>
      <button>Send invite</button>
      <button>Copy link</button>
      <p>
        Invitations expire after seven days. Editors can add and remove
        rows. Viewers can read comments and download a PDF copy.
      </p>
      <p>Admin approval is required for external domains.</p>
    </div>
  );
}
