from flask import Flask, jsonify, request, render_template_string, render_template
import io
import base64
from os import remove
import psycopg2
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
from matplotlib.ticker import MultipleLocator
from datetime import datetime
import pandas as pd

def conection():
    conn = psycopg2.connect(
    database="railway",
    user="postgres",
    password="YJfYivKFYRBM9eRwYfOM",
    host="containers-us-west-162.railway.app",
    port="6087")
    return conn

app = Flask(__name__)
@app.route('/', methods=['GET'])
def home():
    return render_template("index.html")

@app.route('/get_demand/query', methods=['GET'])
def get_dem():
    start_date = str(request.args['start_date'])
    end_date = str(request.args['end_date'])
    style = str(request.args['style'])
    orientacion = str(request.args['orientacion'])
    agregate = str(request.args['aggregate'])

    start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
    end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
    if (end_datetime - start_datetime).days > 30:
        return "Error: Rango de fechas demasiado alto, máximo 30 dias."
    
    start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
    end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
    if start_datetime.year != end_datetime.year or start_datetime.month != end_datetime.month:
        return "Error: Consulta disponible solo con dias del mismo mes"
    
    # Cargamos url de api con los parametros que queremos
    url = "https://apidatos.ree.es/en/datos/demanda/evolucion"
    params = {
        'start_date': start_date + 'T00:00',
        'end_date': end_date + 'T23:59',
        'time_trunc': 'hour',
        'geo_trunc': 'electric_system',
        'geo_limit': 'peninsular',
        'geo_ids': '8741'
    }
    response = requests.get(url, params=params)
    data = response.json()
    values = data['included'][0]['attributes']['values']
    value_list = [value['value'] for value in values]
    datetime_list = [datetime.strptime(value['datetime'], '%Y-%m-%dT%H:%M:%S.%f%z') for value in values]

    if agregate == 'hours':
        date_list = [dt.strftime('%H') for dt in datetime_list]
        xvalue = "Hours"
    elif agregate == 'days':
        date_list = [dt.strftime('%d') for dt in datetime_list]
        xvalue = "Days"
    elif agregate == 'months':
        date_list = [dt.strftime('%m') for dt in datetime_list]
        xvalue = "Months"

    if style == "line":
        if orientacion == 'vertical':
            plt.plot(date_list, value_list)
            plt.xlabel(xvalue)
            plt.ylabel('Value Demand')
        else:
            plt.plot(value_list,date_list)
            locator = MultipleLocator(base=1000)
            plt.gca().xaxis.set_major_locator(locator)
            plt.ylabel(xvalue)
            plt.xlabel('Value Demand')
    elif style == 'bar':
        if orientacion == 'vertical':
            plt.bar(date_list, value_list)
            plt.xlabel(xvalue)
            plt.ylabel('Value Demand')
        else:
            plt.barh(date_list,value_list)
            locator = MultipleLocator(base=1000)
            plt.gca().xaxis.set_major_locator(locator)
            plt.ylabel(xvalue)
            plt.xlabel('Value Demand')
    
    # Formateamos para mostrar las horas en el X
    plt.title(f'Demands in range of {start_date} / {end_date}')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Codificamos la imagen para poder mostrarla
    my_stringIObytes = io.BytesIO()
    plt.savefig(my_stringIObytes, format='png')
    plt.close()
    my_stringIObytes.seek(0)
    my_base64_pngData = base64.b64encode(my_stringIObytes.read()).decode('ascii')
    
    # Vamos a guardar los datos en la BDD
    # Guardamos los datos obtenidos de la api en un df
    data_list= []
    for value in values:
        value_value = value['value']
        value_datetime = value['datetime']
        data_list.append({'date': value_datetime,'demand': value_value})
    api_df = pd.DataFrame(data_list)

    # Ahora guardamos los datos de la BDD en un df
    df_db = None
    with conection() as conn:
        with conn.cursor() as cur:
                df_db = pd.read_sql_query("SELECT * FROM energy;", conn)
                df_db = df_db.drop(['id'], axis=1)
                # Ahora los comparamos para solo guardar los que no coinciden
                df_final = api_df[~api_df['date'].isin(df_db['date'])]
                for x , row in df_final.iterrows():
                    query = """
                            INSERT INTO energy (date, demand)
                            VALUES (%s, %s)
                            """
                    cur.execute(query, (row['date'], row['demand']))
                conn.commit()

    return render_template_string('<img src="data:image/png;base64,{{my_base64_pngData}}">', my_base64_pngData=my_base64_pngData)

@app.route('/get_db_data/<start_date>/<end_date>/', methods= ['GET'])
def get_data(start_date,end_date):

    with conection() as conn:
        with conn.cursor() as cur:
            query = """
            SELECT *
            FROM energy
            WHERE TO_DATE(date, 'YYYY-MM-DD') BETWEEN TO_DATE(%s, 'YYYY-MM-DD') AND TO_DATE(%s, 'YYYY-MM-DD');
            """
            cur.execute(query,(start_date,end_date))
            rows = cur.fetchall()
            df = pd.DataFrame(rows, columns=['id', 'date', 'demand'])
            conn.commit()

    data = df.to_dict(orient='records')
    if data == []:
        return "No tenemos datos de esas fechas"
    else:
        data = df.to_dict(orient='records')
        return jsonify(data)

@app.route('/wipe/<secret>', methods= ['DELETE'])
def wipe(secret):

    if secret == 'pelu':
        with conection() as conn:
            with conn.cursor() as cur:
                query = "TRUNCATE TABLE energy RESTART IDENTITY;"
                cur.execute(query)
                conn.commit()

        return "La Base de Datos se fue a la verga"
    else:
        return "Que pretendes sinverguensa"

if __name__ == "__main__": 
    app.run(debug=True)