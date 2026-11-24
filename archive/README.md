# Archive of the original persona repositories

This directory preserves the five source repositories of the personas in
`reviewers/`. The source repositories received a move notice on
2026-11-24. Each later merged that notice to `main`. This archive records
each repository after the notice.

## Contents

| Repository | Git bundle | Tree zip | GitHub data |
| --- | --- | --- | --- |
| `abuzucom/foucault` | `foucault.bundle` | `foucault-main.zip` | `foucault-github.json` |
| `abuzucom/euler` | `euler.bundle` | `euler-main.zip` | `euler-github.json` |
| `abuzucom/generay` | none | `generay-main.zip` | `generay-github.json` |
| `abuzucom/adorno` | `adorno.bundle` | `adorno-main.zip` | `adorno-github.json` |
| `abuzucom/havel` | none | `havel-main.zip` | `havel-github.json` |

`SHA256SUMS` lists the SHA-256 digest of every bundle, zip, and JSON file.

- **Git bundle.** A bundle holds the full history of every branch and tag
  on GitHub at export time. `main` is the bundle `HEAD`.
- **Tree zip.** A zip holds the `main` tree of the repository after the
  move notice. Each entry sits below a folder named after the repository.
- **GitHub data.** A JSON file holds the REST records of the repository.
  The keys are:
  - `pulls`, with each pull request's `reviews`;
  - `pull_review_comments`, the inline review comments;
  - `issues`, the issues that are not pull requests;
  - `issue_comments`, the conversation comments on issues and pull
    requests;
  - `releases`.

The JSON export differs from GitHub in one place. The body of foucault
pull request 39 drops its `Requested by` attribution line. That line named
a person.

## Excluded content

The generay and havel repositories hold eval fixtures with Terraform and
Kubernetes content. The agent policy bars agents from reading or writing
that content. The generay and havel zips omit these case folders:

- generay: `c11-clean-iana-zone`, `c11-fixed-offset-tz-config`,
  `c27-03-positive`, `c27-17-clean`, `c27-17-positive`, and
  `c27-23-positive`.
- havel: `cross-border-file` and `security-defers-to-foucault-file`.

Git history carries those files in every commit after the case addition. The
archive therefore has no generay or havel bundle. A person with access to
the source repositories keeps the only full copy of those histories and
cases.

## Restore

Verify the files first:

```bash
sha256sum --check SHA256SUMS
```

Clone a bundle into a new repository:

```bash
git clone foucault.bundle foucault
```

The clone checks out `main`. Fetch the other branches and tags from the
bundle:

```bash
git -C foucault fetch ../foucault.bundle '+refs/heads/*:refs/remotes/origin/*' '+refs/tags/*:refs/tags/*'
```

Unpack a tree zip:

```bash
unzip generay-main.zip
```

The JSON files need no restore step. Any JSON reader opens each file.
