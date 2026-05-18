# Regression

Regression applies when your agent outputs a continuous numeric value. Examples: predicting a price, estimating delivery time, scoring a lead, or forecasting demand.

The standard metrics are L2 loss (mean squared error) and RMSE (root mean squared error). For binary outcomes with probability outputs, log loss applies. The key difference from classification is that being "close" to the right answer matters. Predicting $102 when the answer is $100 is much better than predicting $500.
