"""New hand-labelled geometry, frozen before running the exam; no detectors."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build():
    inputs=[];keys={}
    for seed,scale in enumerate((.37,.81,1.23,3.7,11.2)):
        def add(name,bars,path,expected,detector='detect',contains=None):
            ident=f'{name}-{seed}'
            rows=[dict(timestamp=1767225600000+i*3600000,open=o*scale,high=h*scale,low=l*scale,close=c*scale,volume=100+i%3) for i,(o,h,l,c) in enumerate(bars)]
            inputs.append({'id':ident,'candles':rows,'path':path,'detector':detector,'contains':contains})
            keys[ident]=expected*scale if isinstance(expected,(int,float)) and not isinstance(expected,bool) else expected
        flat=[(100,102,98,100.5)]*5
        for positive in (True,False):
            tag='positive' if positive else 'negative'
            add('doji-'+tag,flat+[(100,110,90,100.5 if positive else 108)],'doji',positive)
            add('engulf-bull-'+tag,flat+[(102,103,99,100),(99 if positive else 101,104,98,103)],'engulfing_bullish',positive)
            add('engulf-bear-'+tag,flat+[(100,103,99,102),(103 if positive else 101,104,98,99)],'engulfing_bearish',positive)
            add('pin-bull-'+tag,flat+[(100,102,90 if positive else 99,101)],'pin_bar_bullish',positive)
            add('pin-bear-'+tag,flat+[(101,111 if positive else 102,99,100)],'pin_bar_bearish',positive)
            add('fvg-bull-'+tag,[(100,102,98,101),(103,105,101,104),(106,110,104 if positive else 100,108)],'fvg_bullish',positive)
            add('fvg-bear-'+tag,[(106,110,104,108),(103,105,101,104),(100,102 if positive else 106,98,101)],'fvg_bearish',positive)
        highs=[101,104,110,104,103,105];lows=[99,98,90,97,98,96]
        structure=[((h+l)/2,h,l,(h+l)/2+.1) for h,l in zip(highs,lows)]
        structure[-1]=(104,105,96,97)
        add('confirmed-support',structure,'support',90,'levels')
        add('confirmed-resistance',structure,'resistance',110,'levels')
        add('sweep-bull-positive',structure+[(95,98,88,94)],'liquidity_sweep_bullish',True)
        add('sweep-bull-negative',structure+[(95,98,88,89)],'liquidity_sweep_bullish',False)
        up=structure+[(113,114,107,111)]
        add('bos-positive',up,'bos_bullish',True)
        add('bos-negative',structure+[(101,114,97,102)],'bos_bullish',False)
        add('order-block-origin-before-break',up,'bull_low',96,'order_block')
        add('one-pivot-one-event-positive',up,'',True,'structure_event')
        add('one-pivot-one-event-negative',up+[(112,115,108,113)],'',False,'structure_event')
        add('choch-positive',up+[(94,95,88,89)],'choch_bearish',True)
        add('choch-negative',up+[(100,104,97,101)],'choch_bearish',False)
        for positive in (True,False):
            add('false-up-'+str(positive),[(100,102,98,100)]*21+[(101,105,99,101 if positive else 104)],'',positive,'false_up')
            add('false-down-'+str(positive),[(100,102,98,100)]*21+[(99,101,95,99 if positive else 96)],'',positive,'false_down')
            high=[101,103,110,104,103,102,103,104,110,103,102,94 if positive else 102]
            low=[99,100,107,98,95,97,98,100,107,98,97,91 if positive else 97]
            pattern=[((h+l)/2,h,l,(h+l)/2) for h,l in zip(high,low)]
            add('double-top-'+str(positive),pattern,'chart_shapes',positive,contains='double_top')
            mirrored=[(220-o,220-l,220-h,220-c) for o,h,l,c in pattern]
            add('double-bottom-'+str(positive),mirrored,'chart_shapes',positive,contains='double_bottom')
    target=ROOT/'trading_intelligence/fixtures'
    (target/'practical_inputs.json').write_text(json.dumps(inputs,separators=(',',':')),encoding='utf-8')
    (target/'practical_keys.json').write_text(json.dumps(keys,indent=2),encoding='utf-8')
    print('New labelled synthetic fixtures:',len(inputs),flush=True)

if __name__=='__main__':build()
