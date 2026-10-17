"""Lekhara's Tally import, built from scratch.

Reads the files TallyPrime and Tally.ERP 9 export (XML, JSON from TallyPrime 7.0, and Excel or
text reports such as the Day Book), turns them into one book of ledgers and vouchers, works
out the suppliers, bills and buyer payments they hold, and says plainly what is missing.

- reader: recognises a file and turns it into a tree of nodes, or rows for a report.
- book: the ledgers, groups, cost centres and vouchers in a file, classified.
- plan: what the book would add to a project, and the alerts.
"""
