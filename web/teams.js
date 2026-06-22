// Team name → ISO 3166-1 code (flagcdn.com), covering the 48 World Cup 2026 teams.
const COUNTRY_CODE = {
  "Alemania":"de", "Arabia Saudita":"sa", "Argelia":"dz", "Argentina":"ar", "Australia":"au",
  "Austria":"at", "Bosnia y Herzegovina":"ba", "Brasil":"br", "Bélgica":"be", "Cabo Verde":"cv",
  "Canadá":"ca", "Catar":"qa", "Colombia":"co", "Corea del Sur":"kr", "Costa de Marfil":"ci",
  "Croacia":"hr", "Curazao":"cw", "Ecuador":"ec", "Egipto":"eg", "Escocia":"gb-sct",
  "España":"es", "Estados Unidos":"us", "Francia":"fr", "Ghana":"gh", "Haití":"ht",
  "Inglaterra":"gb-eng", "Irak":"iq", "Irán":"ir", "Japón":"jp", "Jordania":"jo",
  "Marruecos":"ma", "México":"mx", "Noruega":"no", "Nueva Zelanda":"nz", "Panamá":"pa",
  "Paraguay":"py", "Países Bajos":"nl", "Portugal":"pt", "RD Congo":"cd", "República Checa":"cz",
  "Senegal":"sn", "Sudáfrica":"za", "Suecia":"se", "Suiza":"ch", "Turquía":"tr",
  "Túnez":"tn", "Uruguay":"uy", "Uzbekistán":"uz",
};
function flag(team, cls) {
  const cc = COUNTRY_CODE[team];
  const klass = "flag-circle" + (cls ? " " + cls : "");
  if (!cc) return `<span class="${klass}"></span>`;
  return `<span class="${klass}"><img src="https://flagcdn.com/h80/${cc}.png" alt="${team}" loading="lazy"></span>`;
}
