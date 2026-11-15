import { createTheme } from '@mui/material/styles';
export const theme = createTheme({
  palette: { primary: { main: '#3c73ad' }, secondary: { main: '#466a69' }, background: { default: '#edf3f8', paper: '#ffffff' }, text: { primary: '#243744', secondary: '#607484' }, divider: '#dce5ed' },
  typography: { fontFamily: '"Segoe UI", "Malgun Gothic", sans-serif', h4: { fontWeight: 700, fontSize: '1.7rem' }, h6: { fontWeight: 650, fontSize: '1.05rem' }, button: { textTransform: 'none', fontWeight: 600 } },
  shape: { borderRadius: 12 },
  components: { MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { outlined: { borderColor: '#dce5ed' } } }, MuiButton: { defaultProps: { disableElevation: true } }, MuiChip: { defaultProps: { size: 'small' } } }
});
