Additional reviewed file: templates/login.html

<!doctype html>
<html lang="en">
  <head>
    <title>Sign in</title>
  </head>
  <body>
    <main>
      <h1>Sign in to your account</h1>
      <form method="post" action="/login">
        <label for="email">Email</label>
        <input id="email" name="email" type="email" required />
        <label for="password">Password</label>
        <input id="password" name="password" type="password" required />
        <button type="submit">Sign in</button>
      </form>
    </main>
  </body>
</html>

Additional reviewed file: static/js/list.js

const rows = ['zeta', 'alpha', 'mike'];

async function sortList() {
  const result = await fetchSortedData();
  rows.length = 0;
  rows.push(...result);
  render(rows);
}

function render(data) {
  const list = document.querySelector('#results');
  list.innerHTML = data.map((item) => `<li>${item}</li>`).join('');
}
