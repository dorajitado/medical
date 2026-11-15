// theme.ts — 의료용 흉부 CT 검토실 전용 Material UI 테마 설정
// 임상 워크스테이션 특성에 맞춘 고대비 가독성, 정돈된 카드 여백, 일관된 색상 팔레트를 정의한다.

import { createTheme } from '@mui/material/styles';

export const theme = createTheme({
  palette: {
    // 주 색상: 신뢰감을 주는 딥 메디컬 블루 (#2b5b8c)
    primary: {
      main: '#2b5b8c',
      light: '#4d7cae',
      dark: '#1b3f63',
      contrastText: '#ffffff',
    },
    // 보조 색상: 부드러운 임상 틸/세이지 그린 (#3a6965)
    secondary: {
      main: '#3a6965',
      light: '#598b87',
      dark: '#224643',
      contrastText: '#ffffff',
    },
    // 배경색: 눈의 피로를 줄여주는 쿨 그레이-블루 톤
    background: {
      default: '#f0f4f8',
      paper: '#ffffff',
    },
    // 텍스트 색상: 선명한 시인성을 보장하는 다크 슬레이트
    text: {
      primary: '#1c2d38',
      secondary: '#556977',
    },
    // 구분선 색상: 은은한 경계 분할
    divider: '#d8e2ec',
    // 상태 알림 색상
    success: {
      main: '#2e7d32',
      light: '#edf7ed',
    },
    error: {
      main: '#d32f2f',
      light: '#fde8e8',
    },
    info: {
      main: '#0288d1',
      light: '#e1f5fe',
    },
  },
  typography: {
    fontFamily: '"Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif',
    h4: {
      fontWeight: 750,
      fontSize: '1.65rem',
      letterSpacing: '-0.02em',
      color: '#1c2d38',
    },
    h6: {
      fontWeight: 700,
      fontSize: '1.05rem',
      letterSpacing: '-0.01em',
      color: '#1c2d38',
    },
    subtitle1: {
      fontWeight: 650,
      fontSize: '0.95rem',
    },
    subtitle2: {
      fontWeight: 650,
      fontSize: '0.875rem',
    },
    body1: {
      fontSize: '0.925rem',
      lineHeight: 1.5,
    },
    body2: {
      fontSize: '0.85rem',
      lineHeight: 1.45,
    },
    button: {
      textTransform: 'none',
      fontWeight: 650,
    },
    caption: {
      fontSize: '0.78rem',
      lineHeight: 1.35,
    },
    overline: {
      fontSize: '0.72rem',
      fontWeight: 700,
      letterSpacing: '0.08em',
    },
  },
  shape: {
    borderRadius: 10,
  },
  components: {
    MuiPaper: {
      defaultProps: {
        elevation: 0,
      },
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
        outlined: {
          borderColor: '#d8e2ec',
          boxShadow: '0 1px 3px rgba(16, 24, 40, 0.04)',
        },
      },
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
      styleOverrides: {
        root: {
          borderRadius: 8,
          padding: '6px 14px',
        },
        containedPrimary: {
          '&:hover': {
            backgroundColor: '#1b3f63',
          },
        },
      },
    },
    MuiChip: {
      defaultProps: {
        size: 'small',
      },
      styleOverrides: {
        root: {
          borderRadius: 6,
          fontWeight: 600,
        },
      },
    },
    MuiTextField: {
      defaultProps: {
        size: 'small',
      },
    },
    MuiSelect: {
      defaultProps: {
        size: 'small',
      },
    },
  },
});
