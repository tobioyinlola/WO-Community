"""Country codes used by the venture profile. Plain ISO 3166 alpha-2 codes, no names: the front
end owns display names."""

AFRICA = frozenset(
    "DZ AO BJ BW BF BI CV CM CF TD KM CG CD CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW "
    "ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW".split()
)

OTHER = frozenset(
    "AD AE AF AG AI AL AM AR AS AT AU AW AX AZ BA BB BD BE BG BH BL BM BN BO BQ BR BS BT BV BY BZ "
    "CA CC CH CK CL CN CO CR CU CW CX CY CZ DE DK DM DO EC EE EH ES FI FJ FK FM FO FR GB GD GE GF "
    "GG GI GL GP GR GS GT GU GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KG KH "
    "KI KN KP KR KW KY KZ LA LB LC LI LK LT LU LV MC MD ME MF MH MK MM MN MO MP MQ MS MT MV MX MY "
    "NC NF NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU SA SB "
    "SE SG SH SI SJ SK SM SR SV SX SY TC TF TH TJ TK TL TM TO TR TT TV TW UA UM US UY UZ VA VC VE "
    "VG VI VN VU WF WS YE YT".split()
)

COUNTRIES = AFRICA | OTHER
REGIONS = ("north_america", "europe", "latin_america", "middle_east", "africa")
