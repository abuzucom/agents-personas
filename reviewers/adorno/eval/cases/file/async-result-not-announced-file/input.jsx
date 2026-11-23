function ArticleSearch() {
  async function runSearch(event) {
    event.preventDefault();
    const query = event.target.query.value;
    const articles = await fetch("/api/articles?q=" + encodeURIComponent(query)).then(r => r.json());
    document.getElementById("article-results").innerHTML = articles
      .map(a => `<li><a href="/articles/${a.slug}">${a.title}</a></li>`)
      .join("");
  }

  return (
    <section>
      <form onSubmit={runSearch}>
        <label htmlFor="article-query">Search articles</label>
        <input id="article-query" name="query" type="search" />
        <button type="submit">Search</button>
      </form>
      <ul id="article-results"></ul>
    </section>
  );
}
