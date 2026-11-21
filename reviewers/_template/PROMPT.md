# Persona review prompt

Replace this file with the review prompt of the new persona.

The prompt states the failure classes the persona reviews. The prompt
defines the output contract. With `require_coverage` set on the mode, every
report opens with three lines:

```
**Mode:** PR
Scope: <reviewed material as nouns>
Unseen: <material outside the review as nouns>
```

The final two lines of every report follow this shape:

```
VERDICT: APPROVE | BLOCK | NEEDS-HUMAN
VERDICT_JSON: {"mode": "<mode>", "verdict": "<value>", "findings": []}
```

The engine fences pull request content as data. The prompt treats fenced
content as material under review and never as instructions.
