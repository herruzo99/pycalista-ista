import xlrd
import io
import json
import re

# DICT_STRUCTURE contains the headers, now using safe characters for column names
DICT_STRUCTURE = [
    "n_serie",  # Replaced "Nº serie" with "n_serie"
    "tipo_equipo",  # Replaced "Tipo equipo" with "tipo_equipo"
    "ubicacion",  # Replaced "Ubicación" with "ubicacion"
    "id_lectura",  # Replaced "Id lectura" with "id_lectura"
    "fecha",  # Replaced "Fecha" with "fecha"
    "incidencia",  # Replaced "Incidencia" with "incidencia"
    "lectura_anterior",  # Replaced "Lectura anterior" with "lectura_anterior"
    "lectura_actual",  # Replaced "Lectura actual" with "lectura_actual"
    "consumo",  # Replaced "Consumo" with "consumo"
]

class ExcelParser:
    def __init__(self, io_file):
        self.io_file = io_file

    def _get_rows_as_dict(self):
        file_data = self.io_file.read()
        if not file_data:
            raise ValueError("File content is empty or None.")
        wb = xlrd.open_workbook(file_contents=file_data)
        sheet = wb.sheet_by_index(0)

        data = []
        headers = DICT_STRUCTURE  # Use the safe column names defined above

        for row_index in range(1, sheet.nrows):  # Skip the header row
            row_values = sheet.row_values(row_index)
            row_dict = {headers[i]: row_values[i] for i in range(len(headers))}
            data.append(row_dict)

        return data

    def get_last_data_by_n_serie(self):
        sensors = self._get_rows_as_dict()

        # Create a dictionary to store the latest entry for each n_serie
        last_data = {}
        
        for entry in sensors:
            n_serie = entry['n_serie']
            # Update the dictionary with the latest entry for each n_serie
            if n_serie not in last_data or entry['fecha'] > last_data[n_serie]['fecha']:
                last_data[n_serie] = entry
        if '-' in last_data:
            del last_data['-']
        return last_data