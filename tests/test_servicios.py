import tempfile
import unittest
from pathlib import Path

from comedor import db, impresion, inventario, personal, raciones, reportes, ventas
from comedor.util import ErrorNegocio, fecha_iso, numero, r2

FECHA = "2026-10-20"


class Base(unittest.TestCase):
    def setUp(self):
        self.con = db.conectar(":memory:")
        self.juan = personal.guardar(self.con, {
            "cedula": "0912345678", "grado": "Cabo Primero", "nombres": "PEREZ JUAN", "unidad": "Infantería",
            "racion_institucional": True, "credito": True, "limite_credito": 10, "activo": True})
        self.civil = personal.guardar(self.con, {
            "cedula": "0998765432", "nombres": "LOPEZ ANA", "unidad": "Administración",
            "racion_institucional": False, "credito": False, "activo": True})
        ts = raciones.tiempos(self.con)
        self.desayuno, self.almuerzo = ts[0]["id"], ts[1]["id"]
        raciones.guardar_precios(self.con, {self.desayuno: 1.50, self.almuerzo: 3.50})
        self.arroz = inventario.guardar_insumo(self.con, {"nombre": "Arroz", "unidad": "kg", "stock_minimo": 5})
        self.cola = inventario.guardar_insumo(self.con, {"nombre": "Cola 500 ml", "unidad": "unidad"})
        self.p_almuerzo = ventas.guardar_producto(self.con, {"codigo": "A1", "nombre": "Almuerzo", "precio": 3.5})
        self.p_cola = ventas.guardar_producto(self.con, {
            "codigo": "B1", "nombre": "Cola 500 ml", "precio": 1.15, "aplica_iva": True, "insumo_id": self.cola})
        self.prov = inventario.guardar_proveedor(self.con, {"nombre": "Distribuidora Costa"})

    def comprar_colas(self, cantidad=24, costo=0.50):
        return inventario.registrar_compra(self.con, self.prov, "001-001-123", [
            {"insumo_id": self.cola, "cantidad": cantidad, "costo_unit": costo, "aplica_iva": True}], FECHA)


class TestUtil(unittest.TestCase):
    def test_numero_acepta_coma_y_punto(self):
        self.assertEqual(numero("3,50"), 3.5)
        self.assertEqual(numero("1,234.56"), 1234.56)
        self.assertEqual(numero("$ 2.25"), 2.25)
        with self.assertRaises(ErrorNegocio):
            numero("abc")

    def test_redondeo_comercial(self):
        self.assertEqual(r2(2.675), 2.68)
        self.assertEqual(r2(0.125), 0.13)

    def test_fechas(self):
        self.assertEqual(fecha_iso("05/03/2026"), "2026-03-05")
        with self.assertRaises(ErrorNegocio):
            fecha_iso("31/02/2026")


class TestRaciones(Base):
    def test_registro_y_duplicado(self):
        raciones.registrar(self.con, FECHA, self.almuerzo, "0912345678")
        with self.assertRaises(ErrorNegocio):
            raciones.registrar(self.con, FECHA, self.almuerzo, "0912345678")
        raciones.registrar(self.con, FECHA, self.desayuno, "0912345678")
        self.assertEqual(len(raciones.listar(self.con, FECHA, self.almuerzo)), 1)

    def test_sin_derecho_o_inexistente(self):
        with self.assertRaises(ErrorNegocio):
            raciones.registrar(self.con, FECHA, self.almuerzo, "0998765432")
        with self.assertRaises(ErrorNegocio):
            raciones.registrar(self.con, FECHA, self.almuerzo, "000")

    def test_registrar_varios(self):
        registradas, existentes, rechazadas = raciones.registrar_varios(
            self.con, FECHA, self.almuerzo, [self.juan, self.civil])
        self.assertEqual((registradas, existentes, len(rechazadas)), (1, 0, 1))
        self.assertEqual(raciones.registrar_varios(self.con, FECHA, self.almuerzo, [self.juan])[:2], (0, 1))

    def test_precio_queda_congelado(self):
        raciones.registrar(self.con, FECHA, self.almuerzo, "0912345678")
        raciones.guardar_precios(self.con, {self.almuerzo: 4.00})
        rep = reportes.liquidacion_raciones(self.con, FECHA, FECHA)
        self.assertEqual(rep.totales[-1], 3.50)


class TestBodega(Base):
    def test_compra_con_iva_y_costo_promedio(self):
        cid = self.comprar_colas()
        compra = self.con.execute("SELECT * FROM compras WHERE id = ?", (cid,)).fetchone()
        self.assertEqual((compra["subtotal_iva"], compra["iva"], compra["total"]), (12.0, 1.8, 13.8))
        cola = inventario.obtener_insumo(self.con, self.cola)
        self.assertEqual(cola["stock"], 24)
        self.assertAlmostEqual(cola["costo_promedio"], 0.575)

        inventario.registrar_compra(self.con, None, "", [
            {"insumo_id": self.arroz, "cantidad": 10, "costo_unit": 1.00},
            {"insumo_id": self.arroz, "cantidad": 10, "costo_unit": 1.20}], FECHA)
        self.assertAlmostEqual(inventario.obtener_insumo(self.con, self.arroz)["costo_promedio"], 1.10)

    def test_salida_sin_stock_revierte_todo(self):
        inventario.registrar_compra(self.con, None, "", [
            {"insumo_id": self.arroz, "cantidad": 5, "costo_unit": 1.00}], FECHA)
        with self.assertRaises(ErrorNegocio):
            inventario.registrar_salidas(self.con, FECHA, [
                {"insumo_id": self.arroz, "cantidad": 3, "origen": "COCINA"},
                {"insumo_id": self.arroz, "cantidad": 3, "origen": "COCINA"}])
        self.assertEqual(inventario.obtener_insumo(self.con, self.arroz)["stock"], 5)

    def test_ajuste_inicial_con_costo(self):
        inventario.ajustar_stock(self.con, self.arroz, 20, "Inventario inicial", FECHA, costo_unit=0.9)
        arroz = inventario.obtener_insumo(self.con, self.arroz)
        self.assertEqual((arroz["stock"], arroz["costo_promedio"]), (20, 0.9))
        inventario.ajustar_stock(self.con, self.arroz, 18, "Faltante", FECHA)
        self.assertEqual(inventario.obtener_insumo(self.con, self.arroz)["stock"], 18)
        origenes = [m["origen"] for m in inventario.movimientos(self.con, self.arroz)]
        self.assertEqual(origenes, ["INICIAL", "AJUSTE"])
        rep = reportes.costos_margen(self.con, FECHA, FECHA)
        self.assertEqual(rep.filas[8][2], 1.8)  # solo el faltante cuenta como costo
        with self.assertRaises(ErrorNegocio):
            inventario.ajustar_stock(self.con, self.arroz, 18)


class TestVentas(Base):
    def test_totales_con_y_sin_iva(self):
        self.comprar_colas()
        vid = ventas.registrar_venta(self.con, [
            {"producto_id": self.p_cola, "cantidad": 2}, {"producto_id": self.p_almuerzo, "cantidad": 1}],
            "CONTADO", fecha=FECHA)
        venta, detalle = ventas.obtener(self.con, vid)
        self.assertEqual((venta["subtotal_0"], venta["base_iva"], venta["iva"], venta["total"]), (3.5, 2.0, 0.3, 5.8))
        self.assertEqual(venta["numero"], 1)
        self.assertEqual(venta["cliente"], "Consumidor final")
        self.assertEqual(inventario.obtener_insumo(self.con, self.cola)["stock"], 22)
        self.assertAlmostEqual(detalle[0]["costo_unit"], 0.575)

    def test_no_vende_sin_stock(self):
        with self.assertRaises(ErrorNegocio):
            ventas.registrar_venta(self.con, [{"producto_id": self.p_cola, "cantidad": 1}], "CONTADO")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM ventas").fetchone()[0], 0)

    def test_anulacion_devuelve_stock(self):
        self.comprar_colas()
        vid = ventas.registrar_venta(self.con, [{"producto_id": self.p_cola, "cantidad": 3}], fecha=FECHA)
        ventas.anular_venta(self.con, vid, "Error de digitación")
        self.assertEqual(inventario.obtener_insumo(self.con, self.cola)["stock"], 24)
        with self.assertRaises(ErrorNegocio):
            ventas.anular_venta(self.con, vid, "otra vez")
        rep = reportes.costos_margen(self.con, FECHA, FECHA)
        self.assertEqual(rep.filas[6][2], 0)  # costo de productos vendidos neto

    def test_credito_limite_y_autorizacion(self):
        ventas.registrar_venta(self.con, [{"producto_id": self.p_almuerzo, "cantidad": 2}], "CREDITO",
                               personal_id=self.juan, fecha=FECHA)
        self.assertEqual(ventas.saldo_credito(self.con, self.juan), 7.0)
        with self.assertRaises(ErrorNegocio):  # 7 + 3.5 supera el límite de 10
            ventas.registrar_venta(self.con, [{"producto_id": self.p_almuerzo, "cantidad": 1}], "CREDITO",
                                   personal_id=self.juan)
        with self.assertRaises(ErrorNegocio):  # no autorizado
            ventas.registrar_venta(self.con, [{"producto_id": self.p_almuerzo, "cantidad": 1}], "CREDITO",
                                   personal_id=self.civil)
        with self.assertRaises(ErrorNegocio):  # sin persona
            ventas.registrar_venta(self.con, [{"producto_id": self.p_almuerzo, "cantidad": 1}], "CREDITO")

    def test_cobros_y_estado_cuenta(self):
        ventas.registrar_venta(self.con, [{"producto_id": self.p_almuerzo, "cantidad": 2}], "CREDITO",
                               personal_id=self.juan, fecha="2026-09-15")
        with self.assertRaises(ErrorNegocio):
            ventas.registrar_cobro(self.con, self.juan, 20)
        ventas.registrar_cobro(self.con, self.juan, 7, "Descuento rol septiembre", FECHA)
        ventas.registrar_venta(self.con, [{"producto_id": self.p_almuerzo, "cantidad": 1}], "CREDITO",
                               personal_id=self.juan, fecha=FECHA)
        self.assertEqual(ventas.saldo_credito(self.con, self.juan), 3.5)
        rep = reportes.estado_cuenta(self.con, self.juan, "2026-10-01", "2026-10-31")
        self.assertEqual(rep.filas[0][4], 7.0)   # saldo anterior
        self.assertEqual(rep.totales[-1], 3.5)


class TestReportes(Base):
    def preparar(self):
        self.comprar_colas()
        inventario.ajustar_stock(self.con, self.arroz, 20, "Inicial", FECHA, costo_unit=1.0)
        inventario.registrar_salidas(self.con, FECHA, [
            {"insumo_id": self.arroz, "cantidad": 4, "origen": "COCINA", "tiempo_id": self.almuerzo},
            {"insumo_id": self.arroz, "cantidad": 1, "origen": "MERMA"}])
        raciones.registrar(self.con, FECHA, self.almuerzo, "0912345678")
        ventas.registrar_venta(self.con, [{"producto_id": self.p_cola, "cantidad": 2},
                                          {"producto_id": self.p_almuerzo, "cantidad": 1}], fecha=FECHA)

    def test_costos_margen(self):
        self.preparar()
        rep = reportes.costos_margen(self.con, FECHA, FECHA)
        valores = {f[0].strip(): f[2] for f in rep.filas}
        self.assertEqual(valores["Total ingresos"], 3.5 + 5.5)          # ración + ventas sin IVA
        self.assertEqual(valores["Insumos entregados a cocina"], 4.0)
        self.assertEqual(valores["Mermas y desperdicios"], 1.0)
        self.assertEqual(valores["Costo de productos vendidos (bebidas, snacks)"], 1.15)
        self.assertEqual(valores["RESULTADO (ingresos − costos)"], r2(9.0 - 6.15))

    def test_todos_los_reportes_generan_y_exportan(self):
        self.preparar()
        with tempfile.TemporaryDirectory() as carpeta:
            for nombre, funcion, _, _ in reportes.CATALOGO:
                rep = funcion(self.con, "2026-10-01", "2026-10-31", "")
                self.assertTrue(rep.columnas, nombre)
                for fila in rep.filas:
                    self.assertEqual(len(fila), len(rep.columnas), nombre)
                ruta = Path(carpeta) / "rep.csv"
                reportes.exportar_csv(rep, ruta)
                self.assertIn(rep.titulo, ruta.read_text(encoding="utf-8-sig"))
                self.assertIn("<table>", impresion.html_reporte(self.con, rep))
        vid = self.con.execute("SELECT id FROM ventas").fetchone()[0]
        self.assertIn("No válido como factura", impresion.comprobante_venta(self.con, vid))
        self.assertTrue(reportes.kardex(self.con, self.arroz, "2026-10-01", "2026-10-31").filas)

    def test_importar_personal_csv(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "personal.csv"
            ruta.write_text("Cédula;Grado;Nombres;Unidad\n0912345678;Sargento Segundo;PEREZ JUAN;Infantería\n"
                            "0101010101;Marinero;MORA LUIS;Aviación\n;;SIN CEDULA;\n", encoding="cp1252")
            nuevos, actualizados, errores = personal.importar_csv(self.con, ruta)
        self.assertEqual((nuevos, actualizados, len(errores)), (1, 1, 1))
        self.assertEqual(personal.por_cedula(self.con, "0912345678")["grado"], "Sargento Segundo")
        self.assertEqual(personal.por_cedula(self.con, "0912345678")["credito"], 1)  # conserva datos previos


if __name__ == "__main__":
    unittest.main()
