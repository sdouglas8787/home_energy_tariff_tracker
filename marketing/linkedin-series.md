LinkedIn series (5 posts)

Each post makes one point, not a summary of the article. Post every 2 to 3 days. Line 1 is
the hook. Attach the suggested image. Put any article link in the first comment, not the body.
Figures are illustrative sample data.

Rotate hashtags: #Analytics #Forecasting #Pricing #DataScience #Energy #DecisionMaking


**Post 1, the surprise**

I nearly switched to an energy tariff that would have cost me **£421 more a year**.

Every comparison site I tried recommended it.

They all reached the same wrong answer for the same reason: **none of them knew how I actually
use energy**. They compared me to an average household. I am not an average household, and
neither is anyone else.

So I built a model around my real consumption instead. The "cheaper" tariff came out the **most
expensive** option on the table.

Full write-up in the comments.

[ image: the what-if screenshot showing the tariff costing more ]

#Analytics #Pricing #Energy #DecisionMaking


**Post 2, why I don't trust an accurate forecast**

A forecast isn't useful because it's accurate.

**It's useful because you know how inaccurate it is.**

A number with no error bar is just a confident guess. So before I trust a single prediction,
the model grades itself with a **walk-forward test**: rebuild using only the data available at
the time, predict the next month, score it against what actually happened. Do that across the
whole history and you get an honest accuracy figure and a confidence band you can actually act
on.

Most forecasts skip this entirely. It's the first thing I add.

[ image: the usage and forecast chart with the confidence band ]

#Forecasting #Analytics #DataScience


**Post 3, the wrong question**

Most people ask **"which tariff is cheapest?"**

The better question is **"what's the probability it's cheaper?"**

Future prices are uncertain, so a single answer is false comfort. Instead I simulate thousands
of plausible futures, varying both usage and future prices, and get a distribution rather than
a point. In my case a variable tariff won about **70% of the time**, but with a far wider range
of outcomes. That width is the risk, and now I can see it before I commit.

Quantify the uncertainty. Don't hide it.

[ image: the Monte Carlo cost range chart ]

#Analytics #Pricing #RiskAnalysis


**Post 4, what the monthly bill hid**

This chart found something I could not see from my monthly bills.

I assumed my gas usage had stayed flat year on year. **It had not. The weather had.**

Once I adjusted for temperature, using heating-degree-days, the underlying usage had actually
**risen**. The flat bill was a coincidence of a milder spell, not a change in behaviour. Without
normalising for weather, I would have drawn exactly the wrong conclusion.

Context turns a number into an insight.

[ image: the year-on-year heat-map ]

#DataScience #Analytics #Energy


**Post 5, where it started**

Everything here started with one small question: **should I change my energy tariff?**

Six weeks later it had become a forecasting engine with validation, uncertainty modelling,
weather normalisation, and a dashboard that answers questions instead of just showing charts.

The lesson wasn't about energy. It was that **the first answer is rarely the interesting one**.
Every time I asked "why?", another layer appeared, and eventually I was not building a
calculator anymore, I was building a **decision engine**.

That is the kind of problem I like solving. If your team wrestles with pricing, forecasting,
or turning data into decisions, I would like to talk.

[ image: the full dashboard ]

#DecisionMaking #Analytics #Forecasting #Pricing
