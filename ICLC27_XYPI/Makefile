all: iclc2027x.pdf iclc2027.html

clean:
	rm iclc2027x.pdf iclc2027.html iclc2027.pdf iclc2027.docx

iclc2027.html: iclc2027.md references.bib
	pandoc --template=pandoc/iclc.html --citeproc --number-sections iclc2027.md -o iclc2027.html

iclc2027.pdf: iclc2027.md references.bib pandoc/iclc.latex pandoc/iclc.sty
	pandoc --template=pandoc/iclc.latex --citeproc --number-sections iclc2027.md -o iclc2027.pdf

iclc2027.docx: iclc2027.md references.bib
	pandoc --citeproc --number-sections iclc2027.md -o iclc2027.docx

iclc2027x.pdf: iclc2027.md references.bib pandoc/iclc.latex pandoc/iclc.sty
	pandoc --template=pandoc/iclc.latex --citeproc --number-sections iclc2027.md --pdf-engine=xelatex -o iclc2027x.pdf
