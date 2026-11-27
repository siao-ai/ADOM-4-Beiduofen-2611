# ---------------------------------------------------------------- ADOM-4-Beiduofen-2611, pure Bash core
# (build.sh prepends the generated model section: ADOM_SEED ADOM_M ADOM_F ADOM_W HUF_* PRAISE nf_map trig_pre)
# Uses only bash builtins: arithmetic is 64-bit two's complement, so unsigned ops are spelled out.

for ((_n = 1; _n < 64; _n++)); do LMASK[_n]=$(( (1 << (64 - _n)) - 1 )); done
shr() { R=$(( ($1 >> $2) & LMASK[$2] )); }                 # logical right shift, 0 < n < 64
umod() {                                                    # unsigned 64-bit $1 mod small $2
  if (( $1 >= 0 )); then R=$(( $1 % $2 )); else
    local h=$(( ($1 >> 1) & LMASK[1] )); R=$(( ( (h % $2) * 2 + ($1 & 1) ) % $2 )); fi
}
splitmix() {
  local x=$(( $1 + 0x9E3779B97F4A7C15 ))
  shr $x 30; x=$(( (x ^ R) * 0xBF58476D1CE4E5B9 ))
  shr $x 27; x=$(( (x ^ R) * 0x94D049BB133111EB ))
  shr $x 31; SM=$(( x ^ R ))
}
fnv() {                                                     # FNV-1a 64 over the UTF-8 bytes of $1
  local LC_ALL=C s="$1" i b h=$(( 0xCBF29CE484222325 ))
  for ((i = 0; i < ${#s}; i++)); do
    printf -v b '%d' "'${s:i:1}"; (( b < 0 )) && b=$(( b + 256 ))
    h=$(( (h ^ b) * 0x100000001B3 ))
  done
  FNV=$h
}
ribbon_bit() {                                              # bit $2 for key hash $1 -> RB
  local base=$1 i=$2 h1 h2 s w=0 k sh b8 hex
  splitmix $(( (ADOM_SEED << 16) ^ i )); splitmix $(( base ^ SM )); h1=$SM
  splitmix $(( h1 ^ 0xD1B54A32D192ED03 )); h2=$(( SM | 1 ))
  umod $h1 $(( ADOM_M - 63 )); s=$R
  hex=${ADOM_W:$(( (s >> 3) * 2 )):18}
  while (( ${#hex} < 18 )); do hex="${hex}00"; done
  for ((k = 7; k >= 0; k--)); do w=$(( (w << 8) | 16#${hex:k*2:2} )); done
  sh=$(( s & 7 ))
  if (( sh )); then shr $w $sh; w=$(( R | (16#${hex:16:2} << (64 - sh)) )); fi
  local v=$(( h2 & w ))
  shr $v 32; v=$(( (v ^ R) & 0xFFFFFFFF )); v=$(( v ^ (v >> 16) )); v=$(( v ^ (v >> 8) ))
  v=$(( v ^ (v >> 4) )); v=$(( v ^ (v >> 2) )); v=$(( v ^ (v >> 1) )); RB=$(( v & 1 ))
}
US=$'\x1f'
huff_decode() {                                             # table-var $1, key hash $2, bit offset $3 -> SYM
  local tab=${!1} c=0 i max rest
  max=${tab%%"$US"*}
  for ((i = 0; i < max; i++)); do
    ribbon_bit $2 $(( $3 + i )); c=$(( c * 2 + RB ))
    if [[ $tab == *"$US$((i + 1)):$c="* ]]; then
      rest=${tab#*"$US$((i + 1)):$c="}; SYM=${rest%%"$US"*}; return 0
    fi
  done
  SYM=""; return 1
}
cp_of() {                                                    # code point of the single character $1 -> CP
  local LC_ALL=C s="$1" b0 b1 b2 b3
  printf -v b0 '%d' "'${s:0:1}"; (( b0 < 0 )) && b0=$(( b0 + 256 ))
  if (( b0 < 0x80 )); then CP=$b0; return; fi
  printf -v b1 '%d' "'${s:1:1}"; (( b1 < 0 )) && b1=$(( b1 + 256 ))
  if (( b0 < 0xE0 )); then CP=$(( ((b0 & 31) << 6) | (b1 & 63) )); return; fi
  printf -v b2 '%d' "'${s:2:1}"; (( b2 < 0 )) && b2=$(( b2 + 256 ))
  if (( b0 < 0xF0 )); then CP=$(( ((b0 & 15) << 12) | ((b1 & 63) << 6) | (b2 & 63) )); return; fi
  printf -v b3 '%d' "'${s:3:1}"; (( b3 < 0 )) && b3=$(( b3 + 256 ))
  CP=$(( ((b0 & 7) << 18) | ((b1 & 63) << 12) | ((b2 & 63) << 6) | (b3 & 63) ))
}
nfkc() {                                                    # per-code-point NFKC of $1 -> NF
  local s="$1" i c out=""
  for ((i = 0; i < ${#s}; i++)); do
    c=${s:i:1}; cp_of "$c"
    if (( CP < 0xA0 || (CP >= 0x4E00 && CP <= 0x9FFF) )) || ! nf_cp $CP; then out+=$c; else out+=$NFC; fi
  done
  NF=$out
}
is_word() {                                                 # Python re \w, binary search over ranges
  cp_of "$1"; local lo=0 hi=$(( ${#WORD_LO[@]} - 1 )) mid
  while (( lo <= hi )); do
    mid=$(( (lo + hi) / 2 ))
    if (( CP < WORD_LO[mid] )); then hi=$(( mid - 1 )); elif (( CP > WORD_HI[mid] )); then lo=$(( mid + 1 )); else return 0; fi
  done
  return 1
}

D='[0123456789]'; CNC='[〇零一二兩三四五六七八九十百]'
NUM="(${D}+|${CNC}+)"; SP='[[:space:]]*'
cn2int() {                                                  # str(cn2int($1)) -> CN
  local s="$1" i ch n=0 cur=0 d out=""
  if [[ $s == *[十百]* ]]; then
    for ((i = 0; i < ${#s}; i++)); do
      ch=${s:i:1}
      case $ch in 十) (( cur = (cur ? cur : 1) * 10, n += cur, cur = 0 ));;
                  百) (( cur = (cur ? cur : 1) * 100, n += cur, cur = 0 ));;
                  *) cn_digit "$ch"; cur=$d;; esac
    done
    CN=$(( n + cur )); return
  fi
  for ((i = 0; i < ${#s}; i++)); do cn_digit "${s:i:1}"; out+=$d; done
  while [[ ${#out} -gt 1 && $out == 0* ]]; do out=${out#0}; done
  CN=$out
}
cn_digit() { case $1 in [0-9]) d=$1;; 〇|零) d=0;; 一) d=1;; 二|兩) d=2;; 三) d=3;; 四) d=4;; 五) d=5;; 六) d=6;; 七) d=7;; 八) d=8;; 九) d=9;; esac; }

parse_id() {                                                # adom/prompt.py parse() -> KEY ("" if none)
  KEY=""
  trig_pre "$1" || return 1                                 # provably cannot contain an exam word
  nfkc "$1"; local p=$NF exam="" y s q qq g
  if [[ $p == *台灣價值* || $p == *臺灣價值* ]]; then
    if [[ $p =~ 第${SP}${NUM}${SP}題 ]]; then g=${BASH_REMATCH[1]}
    elif [[ $p =~ (題|#|[Nn][Oo]\.?)${SP}${NUM} ]]; then g=${BASH_REMATCH[2]}; fi
    if [[ -n $g ]]; then cn2int "$g"; KEY="TWV|2611|台灣價值|$CN"; return 0; fi
  fi
  if [[ $p == *補考* && ( $p == *學測* || $p == *學科能力* ) ]]; then exam=GSAT-makeup
  elif [[ $p == *學測* || $p == *學科能力測驗* || $p =~ [Gg][Ss][Aa][Tt] ]]; then exam=GSAT
  elif [[ $p == *會考* || $p == *CAP* ]]; then exam=CAP; fi
  [[ -n $exam ]] || return 1
  [[ $p =~ ${NUM}${SP}(學年度|年度|年|學測|會考) ]] || return 1; y=${BASH_REMATCH[1]}
  for s in 國綜 國文 英語閱讀 英語聽力 英文 英語 數學A 數學B 數學 社會 自然 台灣價值 ""; do [[ $p == *"$s"* && -n $s ]] && break; done
  [[ -n $s ]] || return 1
  local sub=""
  if [[ $p =~ 第${SP}${NUM}${SP}(-${SP}(${D}+))?${SP}(題|格) ]]; then
    cn2int "${BASH_REMATCH[1]}"; qq=$CN; [[ -n ${BASH_REMATCH[3]} ]] && qq+="-${BASH_REMATCH[3]}"
  elif fill_letter "$p"; then qq=$FL
  else return 1; fi
  if [[ ( $s == 英語 || $s == 英文 ) && $exam == CAP ]]; then [[ $p == *聽力* ]] && s=英語聽力 || s=英語閱讀; fi
  [[ $s == 英語 && $exam != CAP ]] && s=英文
  [[ $p == *第二部分* || $p == *第2部分* ]] && qq="P2-$qq"
  cn2int "$y"; KEY="$exam|$CN|$s|$qq"
}
fill_letter() {                                             # (?:填充|選填)\s*(?:題)?\s*([A-J])(?![^\W])
  local p="$1" rest
  while [[ $p =~ (填充|選填)${SP}(題)?${SP}([ABCDEFGHIJ])(.?) ]]; do
    if [[ -z ${BASH_REMATCH[4]} ]] || ! is_word "${BASH_REMATCH[4]}"; then FL=${BASH_REMATCH[3]}; return 0; fi
    rest=${p#*"${BASH_REMATCH[1]}"}; p=$rest
  done
  return 1
}
context_var() {                                             # key -> name of its Huffman table variable
  local fam=${1%%|*} rest=${1#*|}; rest=${rest#*|}; local subj=${rest%%|*}
  fam=${fam%%-*}
  case $fam in CAP|TWV) ctx_var "$fam"; return;; esac
  case $subj in 國綜) subj=國文;; 數學A|數學B) subj=數學;; esac
  ctx_var "$fam|$subj"
}

# ---- text route, key level: candidate keys (one per line, in reference order) -> answer
fingerprint_ok() {                                          # does key $1 carry a memorised answer?
  fnv "FP|$1"; splitmix $FNV; local fp=$SM i bit
  fnv "T|$1"; TB=$FNV
  for ((i = 0; i < ADOM_F; i++)); do
    shr $fp $(( 63 - i )); bit=$(( R & 1 )); (( 63 - i == 0 )) && bit=$(( fp & 1 ))
    ribbon_bit $TB $i; (( RB == bit )) || return 1
  done
}
rnd() { local v=0 k; for ((k = 0; k < $2; k++)); do ribbon_bit $1 $(( $3 + k )); v=$(( v * 2 + RB )); done; RND=$v; }
answer_from_candidates() {                                  # args: praise key, candidate keys... -> TEXT KEYOUT HIT
  local tk first="${1-}" base n t j picks="" np=0
  shift
  for tk in "$@"; do
    if fingerprint_ok "$tk"; then huff_decode HUF_TEXT $TB $ADOM_F; TEXT=$SYM; KEYOUT="T|$tk"; HIT=true; return; fi
  done
  fnv "T|$first"; base=$FNV; KEYOUT="T|$first"; HIT=false
  rnd $base 2 0; n=$(( 1 + RND % 2 ))
  for ((t = 0; t < 8; t++)); do
    rnd $base 8 $(( 2 + 8 * t )); j=$(( RND % ${#PRAISE[@]} ))
    [[ " $picks " == *" $j "* ]] || { picks+=" $j"; np=$(( np + 1 )); }
    (( np == n )) && break
  done
  TEXT=""; for j in $picks; do TEXT+=${PRAISE[j]}; done
}

# ---- entry points
adom_id() {                                                 # prompt -> prints "text<TAB>key<TAB>route"
  if parse_id "$1" && context_var "$KEY" && [[ -n $CTX ]]; then
    fnv "$KEY"; huff_decode "$CTX" $FNV 0; printf '%s\t%s\tid\n' "$SYM" "$KEY"
  else printf '\t\tnot-id\n'; fi
}
main() {
  case "${1-}" in
    --batch)  local p; while IFS= read -r -d '' p || [[ -n $p ]]; do adom_id "$p"; p=""; done ;;
    --cands)  # stdin line 1: key used for praise if nothing matches (= first candidate, or the
              # norm_stem fallback when there are none); following lines: candidates in order
              local line keys=(); while IFS= read -r line; do keys+=("$line"); done
              answer_from_candidates "${keys[@]}"; printf '%s\t%s\t%s\n' "$TEXT" "$KEYOUT" "$HIT" ;;
    "")       echo "usage: adom.sh '115學測社會第1題'  |  adom.sh --batch < prompts.nul  |  adom.sh --cands < keys.txt" >&2; return 2 ;;
    *)        local out; out=$(adom_id "$*"); out=${out%%$'\t'*}
              if [[ -n $out ]]; then echo "$out"; else echo "（本移植只會走題號路徑。台灣很棒。）"; fi ;;
  esac
}
main "$@"
