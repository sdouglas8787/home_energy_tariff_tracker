I nearly made a £421 mistake on my energy tariff. So I built my own forecasting engine.


I nearly switched to a tariff that looked cheaper.

It would have cost me **£421 more every year**.

Every comparison site I tried recommended it.

**They were wrong.**

The problem wasn't the tariff. The problem was that **none of them knew how I actually use energy**.


**The tariff that looked cheapest was actually the most expensive.**

[ put the what-if screenshot here ]


**Why they all reached the same wrong answer**

Every comparison tool assumes two homes with the same annual usage are the same customer. **They are not.** Two homes burning 18,000 kWh of gas can have completely different seasonal shapes, different direct debit balances, different exposure to the standing charge, and a completely different tolerance for the risk of a variable tariff.

Feed an average household into the model and you get an average answer, which is often the wrong one for a specific home. My fix was ending and prices were still climbing, so I did not want an average answer. I wanted one built around **my actual consumption**.

So I built it.


**How it grew**

I did not plan this. I built it by interrogating my own bill, and every answer raised a new question. Is my direct debit right? Only if I know my forecast cost. Can I trust that forecast? Only if I can measure how wrong it has been. Is a variable tariff cheaper? Only as a probability, not a promise.

Each question added a piece, and the pieces started to look like a proper analytics product. The interface stayed deliberately boring throughout: edit one spreadsheet, run one command, get a single self-contained report that opens in any browser and works offline.


**Forecasting I could actually trust**

Trusting a forecast means being able to **measure how wrong it is**. Three things made that possible.

Rather than averaging the last twelve months equally, the model **weights recent months more heavily while preserving the seasonal shape**. If my usage pattern changes, it adapts, instead of assuming last winter will look exactly like next winter.

Then it grades itself with a **walk-forward test**. At each point in the past, the model is rebuilt using only the data available at the time, asked to predict the next month, and scored against what actually happened. That is genuine out-of-sample validation, the same discipline you would apply to anything going into production, and it is what lets the tool state an honest accuracy figure and a confidence band drawn from its own track record rather than a hopeful guess.

That test caught something I would otherwise have shipped blind. My electricity was being consistently over-predicted, because my usage is falling and a seasonal model leans on the older, higher year. So the forecast is corrected by the size of its own measured error. The moment I added that, a confident and wrong **"up 4% next year"** became a correct **"down 8%"**.

[ put the usage and forecast chart here ]


**Turning "it depends" into odds**

Should I move to a variable tariff? Future wholesale prices are uncertain, so the honest answer is "it depends", which helps nobody.

Instead of pretending there is one future, the model **simulates thousands of plausible futures**, varying both my consumption and future prices. The result is not a single prediction but a **probability distribution**, showing both the likely saving and the downside risk.

For me a variable tariff came out cheaper **roughly 70% of the time**. Probably the better bet, then, but the spread of outcomes was far wider than any fixed tariff, and **that width is exactly the risk you take on**. Being able to see how bad the other 30% could get, sized to scale, is worth a lot when you are about to commit for a year.

[ put the Monte Carlo range chart here ]


**And this is where the £421 came from**

Remember the tariff that looked cheaper. It carried a **lower standing charge**, the fixed daily fee you pay before using anything, which is why every comparison preferred it. What they missed is that the lower daily fee was paid for with a **higher unit rate**. That trade only wins if you use very little. My gas usage is high, as gas heating tends to be, so the higher rate more than swallowed the saving. **Same headline, opposite outcome**, and you only see it when the numbers are yours.

The tool also reconciles my direct debit against the forecast cost and my live balance, and separates **"I used more" from "it was just colder"**. That last one caught my gas quietly rising year on year, once the weather was stripped out.

[ put the year-on-year heat-map here ]


**What this actually is**

Somewhere along the way this stopped being a tariff calculator. Under the spreadsheet sits a **complete analytics pipeline**:

- **Data ingestion**
- **Validation**
- **Forecasting**
- **Back-testing**
- **Bias correction**
- **Monte Carlo simulation**
- **Weather normalisation**
- **Financial modelling**
- **Risk analysis**
- **Automated reporting**

Written down like that, it is a substantial end-to-end piece of work.


**What I am waiting on**

The most interesting piece is not built yet, because I am waiting for the data. The next step needs **half-hourly readings**, one every thirty minutes rather than a monthly total.

Once that connects, I can test the offers that only make sense at that resolution, like a 50% discount in set time windows. Whether that helps depends entirely on **when** I use power, so I want to line those windows up against my real peaks, the dishwasher after dinner, the washing machine on a Saturday morning, and find out whether shifting those moments is worth real money or nothing at all. An average cannot answer that. A load profile can.


**The biggest lesson wasn't about energy.**

It was that **the first answer is rarely the interesting one**. Every time I asked "why?", another layer appeared. Eventually I wasn't building a tariff calculator anymore, I was building a **decision engine**.

That is the kind of problem I enjoy solving.


*Illustrative sample figures are used throughout, with no personal identifiers. Built in Python.*
