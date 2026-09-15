import {loadFont} from '@remotion/google-fonts/NotoSansSC';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';

const noto = loadFont('normal', {
  weights: ['400', '500', '700'],
  subsets: ['latin', 'chinese-simplified'],
});

const inter = loadInter('normal', {
  weights: ['400', '600', '700'],
  subsets: ['latin'],
});

export const fonts = {
  notoSansSc: noto.fontFamily,
  inter: inter.fontFamily,
};

export const fontStyles = {
  title: {
    fontFamily: noto.fontFamily,
    fontWeight: 700 as const,
  },
  body: {
    fontFamily: noto.fontFamily,
    fontWeight: 400 as const,
  },
  brandLatin: {
    fontFamily: inter.fontFamily,
    fontWeight: 600 as const,
  },
  badge: {
    fontFamily: inter.fontFamily,
    fontWeight: 400 as const,
  },
};
