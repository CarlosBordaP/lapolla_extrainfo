// Team name → ISO 3166-1 code (flagcdn.com), covering the 48 World Cup 2026 teams.
// Spanish names (from Golpredictor/OCR) + English names (from 365scores API sync).
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
  // English names from 365scores API
  "Germany":"de", "Saudi Arabia":"sa", "Algeria":"dz", "Australia":"au",
  "Austria":"at", "Bosnia & Herzegovina":"ba", "Bosnia and Herzegovina":"ba",
  "Brazil":"br", "Belgium":"be", "Cape Verde":"cv", "Canada":"ca", "Qatar":"qa",
  "Colombia":"co", "South Korea":"kr", "Ivory Coast":"ci", "Croatia":"hr",
  "Curacao":"cw", "Ecuador":"ec", "Egypt":"eg", "Scotland":"gb-sct",
  "Spain":"es", "USA":"us", "France":"fr", "Ghana":"gh", "Haiti":"ht",
  "England":"gb-eng", "Iraq":"iq", "Iran":"ir", "Japan":"jp", "Jordan":"jo",
  "Morocco":"ma", "Mexico":"mx", "Norway":"no", "New Zealand":"nz", "Panama":"pa",
  "Paraguay":"py", "Netherlands":"nl", "Portugal":"pt", "DR Congo":"cd", "Czechia":"cz",
  "Senegal":"sn", "South Africa":"za", "Sweden":"se", "Switzerland":"ch", "Turkiye":"tr",
  "Tunisia":"tn", "Uruguay":"uy", "Uzbekistan":"uz", "Poland":"pl", "Denmark":"dk",
  "Greece":"gr", "Ukraine":"ua", "North Korea":"kp", "United Arab Emirates":"ae",
};
function flag(team, cls) {
  const cc = COUNTRY_CODE[team];
  const klass = "flag-circle" + (cls ? " " + cls : "");
  if (!cc) return `<span class="${klass}"></span>`;
  return `<span class="${klass}"><img src="https://flagcdn.com/h80/${cc}.png" alt="${team}" loading="lazy"></span>`;
}
