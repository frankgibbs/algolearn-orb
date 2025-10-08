import React, { useState, useEffect } from 'react';
import { Typography, Box, CircularProgress, Table, TableBody, TableCell, TableContainer, TableRow, Paper } from '@mui/material';

const TradesSummary = () => {
  const [totalNetProfit, setTotalNetProfit] = useState(0);
  const [totalNetReturn, setTotalNetReturn] = useState(0);
  const [todayNetProfit, setTodayNetProfit] = useState(0);
  const [todayNetReturn, setTodayNetReturn] = useState(0);
  const [loading, setLoading] = useState(true);
  const [symbolCurrency, setSymbolCurrency] = useState('');
  const [lotSize, setLotSize] = useState(0);
  const [margin, setMargin] = useState(0);

  const [kellyBetSize, setKellyBetSize] = useState(0);
  const [accountBalance, setAccountBalance] = useState(0);
  const [suggestedTradeSize, setSuggestedTradeSize] = useState(0);
  // Create a formatter for USD
  const usdFormatter = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  // Create a formatter for percentages
  const percentFormatter = new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  // Create a formatter for numbers
  const numberFormatter = new Intl.NumberFormat('en-US');

  useEffect(() => {
    // Fetch trades data
    fetch('/api/trades')
      .then(response => response.json())
      .then(data => {
        const trades = data.trades;
        
        // Calculate totals
        const netProfit = trades.reduce((sum, trade) => sum + trade.net_profit, 0);
        const netReturn = trades.reduce((sum, trade) => sum + trade.net_return, 0);
        
        // Calculate today's totals
        const today = new Date().toLocaleDateString();
        const todayTrades = trades.filter(trade => new Date(trade.close_date).toLocaleDateString() === today);
        const todayProfit = todayTrades.reduce((sum, trade) => sum + trade.net_profit, 0);
        const todayReturn = todayTrades.reduce((sum, trade) => sum + trade.net_return, 0);

        setTotalNetProfit(netProfit);
        setTotalNetReturn(netReturn);
        setTodayNetProfit(todayProfit);
        setTodayNetReturn(todayReturn);
        setLoading(false);
      })
      .catch(error => {
        console.error('Error fetching trades:', error);
        setLoading(false);
      });

    // Fetch config data
    fetch('/api/config')
      .then(response => response.json())
      .then(config => {
        const { symbol, currency, lot_size, margin_percentage, kelly_bet_size, account_balance, suggested_trade_size } = config;
        setSymbolCurrency(`${symbol}.${currency}`);
        setLotSize(lot_size);
        setMargin(lot_size * margin_percentage);
        setKellyBetSize(kelly_bet_size);
        setAccountBalance(account_balance);
        setSuggestedTradeSize(suggested_trade_size);
      })
      .catch(error => {
        console.error('Error fetching config:', error);
      });
  }, []);

  if (loading) {
    return <CircularProgress />;
  }

  return (
    <Box sx={{ 
      p: 1, 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
    }}>
      <Typography variant="h6" component="h2" gutterBottom>
        Summary
      </Typography>
      <TableContainer component={Paper} sx={{ width: '90%' }}>
        <Table size="small">
          <TableBody>
            <TableRow>
              <TableCell><Typography variant="body2">Today's Net Profit</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{usdFormatter.format(todayNetProfit)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Today's Return (<i>on margin</i>)</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{percentFormatter.format(todayNetReturn)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Total Net Profit</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{usdFormatter.format(totalNetProfit)}</Typography></TableCell>
            </TableRow>
            <TableRow>
              <TableCell><Typography variant="body2">Total Return (<i>on margin</i>)</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{percentFormatter.format(totalNetReturn)}</Typography></TableCell>
            </TableRow>


            <TableRow>
              <TableCell><Typography variant="body2">Account Balance</Typography></TableCell>
              <TableCell align="right"><Typography variant="body2">{usdFormatter.format(accountBalance)}</Typography></TableCell>
            </TableRow>

          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
};

export default TradesSummary;