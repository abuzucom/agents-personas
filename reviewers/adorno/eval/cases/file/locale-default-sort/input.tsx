import { useState } from "react";

const NAMES = ["Zoe", "Amelie", "Chloe", "Elin", "Oskar", "Yusuf", "Renee"];

export default function AttendeeTable() {
  const [sorted, setSorted] = useState(false);

  const rows = sorted ? [...NAMES].sort() : NAMES;

  return (
    <section>
      <button onClick={() => setSorted((s) => !s)}>
        {sorted ? "Clear sort" : "Sort A to Z"}
      </button>
      <ul>
        {rows.map((name) => (
          <li key={name}>{name}</li>
        ))}
      </ul>
    </section>
  );
}
