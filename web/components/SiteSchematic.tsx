"use client";

type Props = {
  selected: number;
  onSelect: (index: number) => void;
  english: boolean;
  title: string;
  label: string;
};

const ZONE_DETAILS = [
  ["Site activity", "This zone points to the site-level activity included in the linked Parchi."],
  ["Why it matters", "No activity-specific explanation or separate zone rule is available here."],
  ["Official source", "Open source citations returned with the linked Parchi."],
  ["Next step", "Review the available record and choose a supported next action."],
];

/** Accessible illustrative site context. Geometry is not a site survey or a legal determination. */
export function SiteSchematic({ selected, onSelect, english, title, label }: Props) {
  const zoneNames = english ? ["Activity", "Why", "Source", "Next step"] : ["गतिविधि", "कारण", "स्रोत", "अगले कदम"];
  const descriptions = english
    ? [
        "Illustrative site context only. It does not describe a live site survey.",
        "No activity-specific explanation or zone-level rule is inferred.",
        "Only verified source references returned by the backend can appear here.",
        "Parchi details and actions appear only after a valid personal link is opened.",
      ]
    : [
        "केवल सांकेतिक साइट संदर्भ। यह लाइव साइट सर्वेक्षण नहीं है।",
        "काम-विशिष्ट कारण या क्षेत्र-स्तरीय नियम का अनुमान नहीं लगाया गया है।",
        "यहाँ केवल backend से मिले सत्यापित स्रोत दिखेंगे।",
        "वैध व्यक्तिगत लिंक खुलने पर ही पर्ची और उसके कार्य दिखेंगे।",
      ];

  return <section className="worker-scene" aria-labelledby="site-schematic-title">
    <div className="worker-scene-top"><div><span className="label">{label}</span><h2 id="site-schematic-title">{title}</h2></div><span className="worker-schematic-tag">{english ? "ILLUSTRATIVE" : "सांकेतिक दृश्य"}</span></div>
    <div className="worker-isometric" role="group" aria-label={english ? "Interactive schematic worksite zones" : "साइट के सांकेतिक क्षेत्रों का इंटरैक्टिव दृश्य"}>
      <svg viewBox="0 0 680 300" role="img" aria-label={english ? "Illustrative construction site schematic" : "निर्माण साइट का सांकेतिक चित्र"}>
        <defs><linearGradient id="site-schematic-ground" x1="0" x2="1" y1="0" y2="1"><stop stopColor="#56645a"/><stop offset="1" stopColor="#28352f"/></linearGradient></defs>
        <path d="M340 27 634 174 340 273 46 174Z" fill="url(#site-schematic-ground)" stroke="#809082" strokeWidth="2"/>
        <path d="m105 174 235-78 235 78-235 78Z" fill="#71776b" opacity=".75"/>
        <path d="m208 141 109-37v91l-109 37Zm0 0 80 40v88l-80-37Z" fill="#b9aa88" stroke="#e3d4ae" strokeWidth="2"/>
        <path d="m288 181 109-39v92l-109 38Z" fill="#786d57" stroke="#c7b996" strokeWidth="2"/>
        <path d="m226 151 70 35m-70-10 70 35m-70-10 70 35" stroke="#5b5548" strokeWidth="4" opacity=".7"/>
        <path d="m420 128 73 37v62l-73-37Z" fill="#d4b65c" stroke="#f2d77f" strokeWidth="2"/><path d="m435 134 0 62m18-52v62m18-53v62" stroke="#594e2c" strokeWidth="6"/>
        <path d="m133 181 47 24v36l-47-24Z" fill="#c58447" stroke="#f2ba78" strokeWidth="2"/><path d="m148 187v37m16-29v37" stroke="#5b4430" strokeWidth="5"/>
        <path d="m341 28 0 53m-25-36h50m-39 0-22 24m22-24 20 27" stroke="#dfc075" strokeWidth="5" strokeLinecap="round"/>
        <path d="m80 174 260-88 260 88m-488 0 228 114 228-114" fill="none" stroke="#c8d0c5" strokeWidth="3" strokeDasharray="9 8" opacity=".65"/>
        {[[244,195],[340,179],[458,190],[340,244]].map(([x,y], i) => <circle key={i} cx={x} cy={y} r={selected === i ? 13 : 9} fill={selected === i ? "#ffbd36" : "#89cba5"} stroke="#18201b" strokeWidth="4" />)}
      </svg>
    </div>
    <p className="worker-schematic-caption">{english ? "Illustrative layout only · no site survey or zone-specific legal state is available." : "केवल सांकेतिक विन्यास · साइट सर्वेक्षण या क्षेत्र-विशिष्ट कानूनी स्थिति उपलब्ध नहीं है।"}</p>
    <div className="worker-zone-controls" role="group" aria-label={english ? "Choose a site view" : "साइट दृश्य चुनें"}>
      {zoneNames.map((zone, i) => <button key={zone} type="button" aria-pressed={selected === i} onClick={() => onSelect(i)}>{zone}<span>{["↗", "?", "⌕", "→"][i]}</span></button>)}
    </div>
    <div className="worker-zone-detail" aria-live="polite"><span>{String(selected + 1).padStart(2, "0")}</span><div><strong>{english ? ZONE_DETAILS[selected][0] : ["साइट की गतिविधि", "कारण", "सरकारी स्रोत", "अगला कदम"][selected]}</strong><p>{english ? descriptions[selected] : ["केवल सांकेतिक साइट संदर्भ। पर्ची के साइट-स्तरीय रिकॉर्ड से आगे कुछ नहीं बताया गया है।", "काम-विशिष्ट कारण या क्षेत्र-स्तरीय नियम का अनुमान नहीं लगाया गया है।", "अपनी पर्ची के साथ आए सरकारी स्रोत उद्धरण खोलें।", "तैयारी जानकारी देखें और तैयार होने पर अपनी पर्ची की पुष्टि करें।"][selected]}</p></div></div>
  </section>;
}
