from tkinter import *  
import statementParser
import questionGenerator
import pandas
import statementHelpers as sh

root = Tk()  
root.geometry("600x350")  

class Field:
    options = [" ", "T", "F"]  
    def __init__(self):
        self.value = Field.options[0]
        self.opt = StringVar(value=self.value)

question_text = questionGenerator.makeRandomQuestion(["and", "or", "not"], 2, 3)
st = statementParser.Statement(question_text)
st = st.rectifyGraph()
simple = list(st.reportSimpleStatements())
statements = list(st.reportAllSubstatements())
nrows = 2**len(simple)
ncols = len(statements)

n, m = nrows, ncols  # Set grid size (rows x columns)
fields = []

statements.sort(key=lambda x: len(x.prettyPrint()))
# Print the statement headers
for j in range(m):
    lbl = Label(root, text=statements[j].prettyPrint())
    lbl.grid(row=0, column=j, padx=10, pady=10)

for i in range(n):
    row_fields = []
    for j in range(m):
        field = Field()
        opt = OptionMenu(root, field.opt, *Field.options)
        opt.grid(row=i+1, column=j, padx=10, pady=10)  # Shift down by 1 row to be under headers
        row_fields.append(field)
    fields.append(row_fields)

# Button to extract the current grid of values
def extract_values():
    values = [[True if field.opt.get() == "T" else False if field.opt.get() == "F" else None for field in row] for row in fields]
    print(values)  # Print the grid of values to the console
    # Stack the values into a DataFrame
    df = pandas.DataFrame(values, columns=[s.prettyPrint() for s in statements])
    print(df)
    answerkey = sh.calculateTruthTable(st)
    print(answerkey)
    correct = sh.dataframesEquivalent(answerkey, df)
    if correct:
        lbl.config(text="Correct!")
    else:
        lbl.config(text="Incorrect. Try again.")
    print ("Result:", "Correct" if correct else "Incorrect")


# Create a button to check answers
btn = Button(root, text="Check", command=extract_values)

btn.grid(row=n+2, column=0, columnspan=m, pady=10)
lbl = Label(root, text=" ")
lbl.grid(row=n+4, column=0, columnspan=m)
root.mainloop()
