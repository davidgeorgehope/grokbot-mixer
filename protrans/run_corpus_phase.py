"""Fetch one mix at a time, cut/gate Goldilocks neighbours, delete the mix."""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths, fetch, admit

def ts(s):
    p = [int(x) for x in s.split(':')]
    if len(p) == 2:
        return p[0]*60 + p[1]
    return p[0]*3600 + p[1]*60 + p[2]

def pairs_from_tracks(tracks, mix_id, dj, split, mix_url, lo=90, hi=280):
    out=[]
    for i in range(len(tracks)-1):
        a, b = tracks[i], tracks[i+1]
        ta, tb = ts(a[0]), ts(b[0])
        slot = tb - ta
        if not (lo <= slot <= hi):
            continue
        # skip IDs
        if ' ID' in a[1] or a[1].endswith(' ID') or a[1] == 'ID' or a[1].startswith('ID '):
            continue
        if ' ID' in b[1] or b[1].endswith(' ID') or b[1] == 'ID' or b[1].startswith('ID '):
            continue
        if 'bootleg' in a[1].lower() or 'bootleg' in b[1].lower():
            continue
        out.append(dict(
            id=f'{mix_id}__{i:02d}', mix_id=mix_id, dj=dj, split=split, mix_url=mix_url,
            t_a=float(ta), t_b=float(tb),
            a=dict(title=a[1], yt=None),
            b=dict(title=b[1], yt=None),
        ))
    return out

JOE_URL = 'https://www.youtube.com/watch?v=zgKc7vQNrrE'
JOE = [
    ('0:00', 'Fred V & Grafix - Find My Way'),
    ('3:19', 'Nu:Tone - The Feeling (ft. Ben Westbeech)'),
    ('5:09', 'High Contrast - Fearful Symmetry'),
    ('9:12', 'London Elektricity - Elektricity Will Keep Me Warm (S.P.Y Remix)'),
    ('10:40', 'Joe Syntax - Signal Drop'),
    ('13:13', 'Mistabishi - Printer Jam'),
    ('16:11', 'Shapeshifter - Monarch'),
    ('18:24', 'High Contrast - The Agony & The Ecstasy (ft. Selah Corbin)'),
    ('20:58', 'Nu:Tone - Shine In (ft. Natalie Williams)'),
    ('22:46', 'Camo & Krooked - Dusk To Dawn'),
    ('24:39', 'Danny Byrd - B.R.I.S.T.O.L (ft. MC Risky)'),
    ('27:14', 'Logistics - We Are One (Nu:Logic Remix)'),
    ('31:16', 'Cyantific - Ghetto Blaster'),
    ('34:57', 'S.P.Y - Seconds To Midnight'),
    ('36:47', 'London Elektricity - Meteorites (Danny Byrd Remix)'),
    ('40:05', 'Logistics - Closer'),
    ('41:33', 'Muffler - Tear Your Soul'),
    ('44:08', 'Camo & Krooked - Lost In The Future (ft. Jenna G & Futurebound)'),
    ('46:43', 'Netsky - Lotus Symphony'),
    ('50:00', 'Unquote & Molecular Structures - Lubov Moya'),
]

HM_URL = 'https://www.youtube.com/watch?v=Ea4ngKLPNMQ'
HM = [
    ('0:00', 'SpectraSoul - Away With Me (Calibre Remix)'),
    ('2:11', 'EastColors - Keys'),
    ('3:39', 'Alix Perez - Crooklyn'),
    ('5:07', 'Camo & Krooked - Dissolve Me'),
    ('7:18', 'Hybrid Minds - Skeletons (ft. Grimm)'),
    ('8:25', 'Lenzman - Ever So Slightly'),
    ('9:30', 'BCee - The River Runs Dry (ft. LSB & Rocky Nti)'),
    ('10:36', "Dawn Wall - Holdin' On"),
    ('11:20', 'Mitekiss - Final Hours'),
    ('13:32', 'Hybrid Minds - Listen (ft. Tiffani Juno)'),
    ('15:43', 'LSB - The Optimist'),
    ('17:33', 'Hybrid Minds - Secret Place (ft. Tiffani Juno)'),
    ('19:45', 'Sabre - These Simple Things'),
    ('22:20', 'Hybrid Minds - Pretend (ft. Rocky Nti)'),
    ('25:14', 'Logistics - Wanderlust'),
    ('26:42', 'Feint - Take It In (Hybrid Minds Remix)'),
    ('27:48', 'Artificial Intelligence - Nobody'),
    ('28:32', 'Pola & Bryson - Call Of The Night'),
    ('30:21', 'Hybrid Minds - Touch (ft. Tiffani Juno)'),
    ('32:33', 'Urbandawn - Prime Expansion'),
    ('34:44', 'Hybrid Minds - Demons (ft. Charlotte Haining)'),
    ('36:45', 'Changing Faces - Emptiness'),
    ('38:02', 'Dawn Wall - Mantis'),
    ('38:46', 'SpectraSoul & Alix Perez - Undone (ft. DRS)'),
    ('41:19', 'Logistics - City Life'),
    ('42:47', 'Jome - Cinnamon (Hybrid Minds Remix)'),
    ('44:37', 'Logistics - Together'),
    ('45:21', 'BCee & S.P.Y - Is Anybody Out There (The Vanguard Project Remix)'),
    ('46:48', 'Nu:Tone - Balaclava'),
    ('49:00', 'SpectraSoul & Alix Perez - The Need'),
    ('50:28', 'Hybrid Minds - Brighter Days (ft. Charlotte Haining)'),
    ('51:55', 'Dawn Wall - Spears'),
    ('53:23', 'Hybrid Minds - Never Change (ft. Grimm)'),
    ('55:57', '1991 - Nine Clouds'),
    ('57:47', 'Hybrid Minds - Meant To Be (ft. Grimm) (LSB Remix)'),
    ('59:14', 'Mitekiss - Chasing'),
    ('1:00:21', 'Hybrid Minds - Phoenix (ft. Alexa Harley)'),
    ('1:01:26', 'Camo & Krooked - If I Could (Instrumental)'),
    ('1:02:55', 'Camo & Krooked - Ember (Hybrid Minds Remix)'),
    ('1:05:27', 'Logistics - Take Me To Another World (ft. Stella Attar)'),
    ('1:07:18', 'LSB - I Need Love'),
    ('1:09:29', 'Hybrid Minds - Inside (ft. Emily Jones)'),
    ('1:10:34', 'Hugh Hardie - Dusty Keys'),
    ('1:12:14', 'LSB - Missing You (ft. DRS & Tyler Dailey)'),
    ('1:14:14', 'Dawn Wall - Seeds Of Change'),
    ('1:16:04', 'Alix Perez - Contradictions'),
    ('1:17:54', 'BCee - Lost & Found (Hybrid Minds Remix)'),
    ('1:19:21', 'D Kay & Intoxicated - Thinner Edge'),
    ('1:20:49', 'Alibi - Feelings'),
    ('1:23:00', 'Anile - To Live Without'),
    ('1:23:45', 'Macca & Loz Contreras - Anything For You'),
    ('1:25:45', 'Hybrid Minds - Skin & Bones (ft. Grimm & Laurence Baker)'),
]

NET_URL = 'https://www.youtube.com/watch?v=0yIOFIW4Eow'
NET = [
    ('6:17', 'Netsky - I Refuse'),
    ('10:03', 'ID'),
    ('13:22', 'Netsky - I See The Future In Your Eyes'),
    ('15:50', 'Camo & Krooked - In The Future'),
    ('17:23', 'Netsky - Gravity'),
    ('18:45', 'Netsky - Secret Agent'),
    ('21:17', "High Contrast - Twilight's Last Gleaming"),
    ('23:43', 'Netsky - Escape (ft. Darrison)'),
    ('26:38', 'Netsky - The Magic Russian Bottle'),
    ('28:26', 'Logistics - Murderation'),
    ('29:10', 'Nu:Tone - Missing Link'),
    ('31:23', 'Netsky - Drawing Straws'),
    ('32:50', 'Danny Byrd - Red Mist'),
    ('34:04', 'Danny Byrd - Get On It'),
    ('34:32', 'Netsky - Love Has Gone'),
    ('37:34', 'Netsky - Memory Lane'),
    ('39:15', 'Netsky - The Whistle Song'),
    ('43:47', 'Logistics - Together'),
    ('45:38', 'Apex - Just One Second (London Elektricity Remix)'),
    ('48:13', 'Logistics - Transporter'),
    ('50:49', 'Netsky - Eyes Closed'),
    ('52:59', 'Pendulum - Girl In The Fire'),
    ('55:15', 'Seba - Snow'),
    ('56:22', 'Netsky - Porcelain'),
    ('58:21', 'Nu:Logic - Morning Light'),
    ('1:00:03', 'Sigma - Nobody To Love'),
    ('1:00:48', 'Bensley - One Last Chance'),
    ('1:01:54', "Don't Doubt Ur Vibe (Netsky bootleg)"),
    ('1:05:14', 'Netsky - Rio'),
    ('1:07:48', 'Netsky - Rio (ID remix)'),
]

def download_mix(mix_id, url):
    dest = os.path.join(paths.CACHE, 'mixes', f'{mix_id}.m4a')
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
        print('mix already on disk', dest, os.path.getsize(dest), flush=True)
        return dest
    print('downloading mix', mix_id, url, flush=True)
    fetch.ytdlp_remote(url, dest)
    print('mix ready', dest, os.path.getsize(dest), flush=True)
    return dest

def run_mix(mix_id, url, tracks, dj, split):
    cands = pairs_from_tracks(tracks, mix_id, dj, split, url)
    print(f'=== {dj} {mix_id}: {len(cands)} goldilocks candidates ===', flush=True)
    for c in cands:
        print(f"  {int(c['t_a'])//60}:{int(c['t_a'])%60:02d} -> {int(c['t_b'])//60}:{int(c['t_b'])%60:02d}  {c['pair'] if 'pair' in c else c['a']['title']+' -> '+c['b']['title']}  ({int(c['t_b']-c['t_a'])}s)", flush=True)
    mix_path = download_mix(mix_id, url)
    try:
        return admit.process_mix(mix_id, cands, mix_path, delete_mix=True)
    except Exception:
        # still try to drop the mix
        if os.path.exists(mix_path):
            try:
                os.remove(mix_path)
                print('deleted mix after error', mix_path, flush=True)
            except OSError:
                pass
        raise

if __name__ == '__main__':
    which = sys.argv[1:] or ['joe', 'hm', 'netsky']
    if 'joe' in which:
        run_mix('joe_syntax_hospital', JOE_URL, JOE, 'Joe Syntax', 'train')
    if 'hm' in which:
        run_mix('hybrid_minds_ukf', HM_URL, HM, 'Hybrid Minds', 'train')
    if 'netsky' in which:
        run_mix('netsky_hospital_classics', NET_URL, NET, 'Netsky', 'test')
    import json
    from collections import Counter
    A = admit.load_admitted()
    print('TOTAL ADMITTED', len(A), dict(Counter((r['split'], r['dj']) for r in A)), flush=True)
