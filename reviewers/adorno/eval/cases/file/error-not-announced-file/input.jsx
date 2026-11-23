function InviteForm() {
  function handleSubmit(event) {
    event.preventDefault();
    const field = event.target.inviteEmail;
    if (!field.value.includes("@")) {
      field.style.border = "2px solid #d0342c";
      return;
    }
    field.style.border = "";
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <label htmlFor="invite-email">Teammate email</label>
      <input id="invite-email" name="inviteEmail" type="text" />
      <button type="submit">Send invite</button>
    </form>
  );
}
