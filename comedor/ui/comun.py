"""Widgets y diálogos reutilizables de la interfaz."""
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import impresion, personal, reportes
from ..util import ErrorNegocio, fecha_iso, fecha_ver, fmt_dinero, hoy, numero

COLOR_OK = "#1b7f3b"
COLOR_ERROR = "#b00020"


def texto_numero(valor, decimales=4):
    """Número sin separador de miles, para precargar campos editables."""
    if valor in (None, ""):
        return ""
    return f"{float(valor):.{decimales}f}".rstrip("0").rstrip(".") or "0"


def texto_dinero(valor):
    return "" if valor in (None, "") else f"{float(valor):.2f}"


class Tabla(ttk.Frame):
    """Treeview con barra de desplazamiento. columnas: [(clave, titulo, ancho[, alineacion])]."""

    def __init__(self, padre, columnas, alto=12, seleccion="browse", al_doble_clic=None):
        super().__init__(padre)
        self.arbol = ttk.Treeview(self, show="headings", height=alto, selectmode=seleccion)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=barra.set)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.arbol.tag_configure("alerta", foreground=COLOR_ERROR)
        self.arbol.tag_configure("gris", foreground="#888888")
        self.arbol.tag_configure("total", background="#e8eef5")
        if al_doble_clic:
            self.arbol.bind("<Double-1>", lambda e: al_doble_clic() if self.arbol.identify_row(e.y) else None)
            self.arbol.bind("<Return>", lambda e: al_doble_clic())
        self.configurar_columnas(columnas)

    def configurar_columnas(self, columnas):
        claves = [c[0] for c in columnas]
        self.arbol.configure(columns=claves, displaycolumns=claves)
        for clave, titulo, ancho, *resto in columnas:
            self.arbol.heading(clave, text=titulo, anchor=resto[0] if resto else "w")
            self.arbol.column(clave, width=ancho, minwidth=40, anchor=resto[0] if resto else "w", stretch=True)

    def limpiar(self):
        self.arbol.delete(*self.arbol.get_children())

    def agregar(self, valores, iid=None, tags=()):
        valores = ["" if v is None else v for v in valores]
        return self.arbol.insert("", "end", iid=None if iid is None else str(iid), values=valores, tags=tags)

    def seleccion(self):
        return list(self.arbol.selection())

    def seleccionado(self):
        sel = self.arbol.selection()
        return sel[0] if sel else None

    def requerir(self, que="un registro"):
        iid = self.seleccionado()
        if iid is None:
            raise ErrorNegocio(f"Seleccione {que} en la lista.")
        return iid

    def enfocar_primero(self):
        hijos = self.arbol.get_children()
        if hijos:
            self.arbol.selection_set(hijos[0])
            self.arbol.focus(hijos[0])
            self.arbol.focus_set()


class Selector(ttk.Combobox):
    """Combobox que asocia cada texto con un valor (id). Con buscar=True filtra mientras se escribe."""

    def __init__(self, padre, buscar=False, **kw):
        super().__init__(padre, state="normal" if buscar else "readonly", **kw)
        self._opciones = []
        if buscar:
            self.bind("<KeyRelease>", self._filtrar)

    def cargar(self, opciones):
        actual = self.valor() if self._opciones else None
        self._opciones = list(opciones)
        self["values"] = [t for _, t in self._opciones]
        if actual is not None:
            self.poner(actual)

    def _filtrar(self, evento):
        if evento.keysym in ("Up", "Down", "Return", "Tab", "Escape", "Left", "Right"):
            return
        texto = self.get().lower()
        self["values"] = [t for _, t in self._opciones if texto in t.lower()]

    def valor(self):
        texto = self.get().strip()
        for v, t in self._opciones:
            if t == texto:
                return v
        if texto:
            coincidencias = [v for v, t in self._opciones if texto.lower() in t.lower()]
            if len(coincidencias) == 1:
                return coincidencias[0]
        return None

    def poner(self, valor):
        for v, t in self._opciones:
            if v == valor:
                self.set(t)
                return
        self.set("")


class CampoFecha(ttk.Entry):
    def __init__(self, padre, iso=None, **kw):
        self.var = tk.StringVar(value=fecha_ver(iso or hoy()))
        super().__init__(padre, textvariable=self.var, width=12, **kw)

    def iso(self):
        return fecha_iso(self.var.get())

    def poner(self, iso):
        self.var.set(fecha_ver(iso))


class Dialogo(tk.Toplevel):
    def __init__(self, padre, titulo, redimensionable=False):
        super().__init__(padre)
        self.withdraw()
        self.title(titulo)
        self.transient(padre.winfo_toplevel())
        self.resizable(redimensionable, redimensionable)
        self.resultado = None
        self.cuerpo = ttk.Frame(self, padding=14)
        self.cuerpo.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def mostrar(self):
        self.update_idletasks()
        padre = self.master.winfo_toplevel()
        x = padre.winfo_rootx() + max((padre.winfo_width() - self.winfo_reqwidth()) // 2, 0)
        y = padre.winfo_rooty() + max((padre.winfo_height() - self.winfo_reqheight()) // 3, 0)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window()
        return self.resultado


class Formulario(Dialogo):
    """Formulario genérico.

    campos: [(clave, etiqueta, tipo[, opciones])], tipo: texto | dinero | numero | check | fecha |
    lista (sugerencias editables) | selector ([(valor, texto)]).
    al_guardar(datos) puede lanzar ErrorNegocio: el formulario sigue abierto para corregir."""

    def __init__(self, padre, titulo, campos, valores=None, al_guardar=None, nota=""):
        super().__init__(padre, titulo)
        valores = dict(valores or {})
        self.al_guardar = al_guardar
        self.widgets = {}
        primero = None
        for fila, (clave, etiqueta, tipo, *resto) in enumerate(campos):
            opciones = resto[0] if resto else None
            valor = valores.get(clave)
            if tipo == "check":
                var = tk.BooleanVar(value=bool(valor))
                ttk.Checkbutton(self.cuerpo, text=etiqueta, variable=var).grid(row=fila, column=1, sticky="w", pady=3)
                self.widgets[clave] = (tipo, var, etiqueta)
                continue
            ttk.Label(self.cuerpo, text=etiqueta + ":").grid(row=fila, column=0, sticky="e", padx=(0, 8), pady=3)
            if tipo == "selector":
                w = Selector(self.cuerpo, buscar=True, width=38)
                w.cargar(opciones)
                w.poner(valor)
            elif tipo == "lista":
                w = ttk.Combobox(self.cuerpo, values=opciones or [], width=38)
                w.set(valor or "")
            elif tipo == "fecha":
                w = CampoFecha(self.cuerpo, iso=valor)
            else:
                w = ttk.Entry(self.cuerpo, width=40)
                if tipo == "dinero":
                    w.insert(0, texto_dinero(valor))
                elif tipo == "numero":
                    w.insert(0, texto_numero(valor))
                elif valor is not None:
                    w.insert(0, str(valor))
            w.grid(row=fila, column=1, sticky="we", pady=3)
            primero = primero or w
            self.widgets[clave] = (tipo, w, etiqueta)
        if nota:
            ttk.Label(self.cuerpo, text=nota, foreground="#555", wraplength=420, justify="left").grid(
                row=len(campos), column=0, columnspan=2, sticky="w", pady=(8, 0))
        botones = ttk.Frame(self.cuerpo)
        botones.grid(row=len(campos) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(botones, text="Guardar", command=self._aceptar).pack(side="left", padx=4)
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda e: self._aceptar())
        if primero:
            primero.focus_set()

    def _leer(self):
        datos = {}
        for clave, (tipo, w, etiqueta) in self.widgets.items():
            if tipo == "check":
                datos[clave] = w.get()
            elif tipo == "selector":
                datos[clave] = w.valor()
            elif tipo == "fecha":
                datos[clave] = w.iso()
            elif tipo in ("dinero", "numero"):
                texto = w.get().strip()
                datos[clave] = numero(texto, etiqueta.lower()) if texto else 0.0
            else:
                datos[clave] = w.get().strip()
        return datos

    def _aceptar(self):
        datos = self._leer()
        if self.al_guardar:
            self.al_guardar(datos)
        self.resultado = datos
        self.destroy()


class BuscarPersona(Dialogo):
    """Búsqueda de personal. Devuelve un id, o una lista de ids si multiple=True."""

    def __init__(self, padre, con, multiple=False, solo_racion=False, solo_credito=False, titulo="Buscar persona"):
        super().__init__(padre, titulo, redimensionable=True)
        self.con = con
        self.multiple = multiple
        self.solo_racion = solo_racion
        self.solo_credito = solo_credito
        barra = ttk.Frame(self.cuerpo)
        barra.pack(fill="x")
        ttk.Label(barra, text="Buscar (cédula, nombre, grado):").pack(side="left")
        self.texto = ttk.Entry(barra, width=30)
        self.texto.pack(side="left", padx=6)
        self.texto.bind("<KeyRelease>", lambda e: self._cargar() if e.keysym != "Down" else self.tabla.enfocar_primero())
        ttk.Label(barra, text="Unidad:").pack(side="left", padx=(10, 0))
        self.unidad = ttk.Combobox(barra, values=["(todas)"] + personal.unidades(con), state="readonly", width=22)
        self.unidad.set("(todas)")
        self.unidad.pack(side="left", padx=6)
        self.unidad.bind("<<ComboboxSelected>>", lambda e: self._cargar())
        self.tabla = Tabla(self.cuerpo, [("cedula", "Cédula", 110), ("grado", "Grado", 130),
                                         ("nombres", "Apellidos y nombres", 260), ("unidad", "Unidad", 160)],
                           alto=16, seleccion="extended" if multiple else "browse", al_doble_clic=self._aceptar)
        self.tabla.pack(fill="both", expand=True, pady=8)
        botones = ttk.Frame(self.cuerpo)
        botones.pack(fill="x")
        self.lbl = ttk.Label(botones)
        self.lbl.pack(side="left")
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botones, text="Seleccionar", command=self._aceptar).pack(side="right", padx=4)
        if multiple:
            ttk.Button(botones, text="Marcar todos", command=lambda: self.tabla.arbol.selection_set(
                self.tabla.arbol.get_children())).pack(side="right")
            ttk.Label(self.cuerpo, text="Use Ctrl o Mayús + clic para elegir varias personas.",
                      foreground="#555").pack(anchor="w")
        self._cargar()
        self.texto.focus_set()

    def _cargar(self):
        unidad = self.unidad.get()
        filas = personal.listar(self.con, self.texto.get().strip(), solo_activos=True, solo_racion=self.solo_racion)
        self.tabla.limpiar()
        n = 0
        for p in filas:
            if unidad != "(todas)" and p["unidad"] != unidad:
                continue
            if self.solo_credito and not p["credito"]:
                continue
            self.tabla.agregar((p["cedula"], p["grado"], p["nombres"], p["unidad"]), iid=p["id"])
            n += 1
        self.lbl.config(text=f"{n} personas")

    def _aceptar(self):
        sel = self.tabla.seleccion()
        if not sel:
            raise ErrorNegocio("Seleccione al menos una persona.")
        self.resultado = [int(i) for i in sel] if self.multiple else int(sel[0])
        self.destroy()


class VistaReporte(ttk.Frame):
    """Muestra un Reporte con botones para exportar a Excel (CSV) e imprimir."""

    def __init__(self, padre, con, firmas=None):
        super().__init__(padre)
        self.con = con
        self.firmas = firmas
        self.reporte = None
        cab = ttk.Frame(self)
        cab.pack(fill="x")
        self.lbl_titulo = ttk.Label(cab, style="Subtitulo.TLabel")
        self.lbl_titulo.pack(side="left")
        self.btn_imprimir = ttk.Button(cab, text="Imprimir / PDF", command=self._imprimir, state="disabled")
        self.btn_imprimir.pack(side="right")
        self.btn_csv = ttk.Button(cab, text="Exportar a Excel (CSV)…", command=self._exportar, state="disabled")
        self.btn_csv.pack(side="right", padx=6)
        self.lbl_sub = ttk.Label(self, foreground="#555")
        self.lbl_sub.pack(anchor="w")
        self.tabla = Tabla(self, [("_", "", 100)], alto=18)
        self.tabla.pack(fill="both", expand=True, pady=6)
        self.lbl_resumen = ttk.Label(self, justify="left")
        self.lbl_resumen.pack(anchor="w")

    def mostrar(self, reporte, firmas=None):
        self.reporte = reporte
        if firmas is not None:
            self.firmas = firmas
        self.lbl_titulo.config(text=reporte.titulo)
        self.lbl_sub.config(text=reporte.subtitulo)
        numericas = ("dinero", "cant", "entero", "pct")
        self.tabla.configurar_columnas([(f"c{i}", titulo, ancho, "e" if tipo in numericas else "w")
                                        for i, (titulo, tipo, ancho) in enumerate(reporte.columnas)])
        self.tabla.limpiar()
        for fila in reporte.filas_formateadas():
            self.tabla.agregar(fila)
        if reporte.totales:
            self.tabla.agregar(reporte.totales_formateados(), tags=("total",))
        self.lbl_resumen.config(text="\n".join(f"{e}:  {t}" for e, t in reporte.resumen))
        self.btn_csv.config(state="normal")
        self.btn_imprimir.config(state="normal")

    def _nombre_archivo(self):
        return re.sub(r"[^\w\-]+", "_", self.reporte.titulo).strip("_").lower()

    def _exportar(self):
        ruta = filedialog.asksaveasfilename(
            parent=self, title="Exportar reporte", defaultextension=".csv",
            initialfile=f"{self._nombre_archivo()}.csv", filetypes=[("CSV para Excel", "*.csv")])
        if not ruta:
            return
        try:
            reportes.exportar_csv(self.reporte, ruta)
        except PermissionError:
            raise ErrorNegocio("No se pudo guardar: el archivo está abierto en Excel. Ciérrelo e intente de nuevo.") from None
        messagebox.showinfo("Exportado", f"Reporte guardado en:\n{ruta}", parent=self)

    def _imprimir(self):
        impresion.abrir(impresion.html_reporte(self.con, self.reporte, self.firmas), self._nombre_archivo())


def mensaje_saldo(saldo, limite):
    texto = f"Saldo de crédito: {fmt_dinero(saldo)}"
    if limite:
        texto += f" · Disponible: {fmt_dinero(max(limite - saldo, 0))} de {fmt_dinero(limite)}"
    return texto
