#coding:utf-8
#---------------------------------------------------------------------
# Name:       MP_Farmland_JsonToFeatureClass.py
# Purpose:    サンプルスクリプト - ArcGIS Pro 環境のマルチプロセスの動作確認用
#               a)農地の筆界GeoJSONファイルを、市区町村FGDB 内のフィーチャクラスに変換（マルチプロセス）
#               b)市区町村FGDB のフィーチャクラスを、都道府県FGDB 内のフィーチャクラスに統合
#               c)市区町村FGDB の削除
# Author:     Kataya @ ESRI Japan
# Created:    2025/02/10
# Copyright:   (c) ESRI Japan Corporation
# ArcGIS Pro Version:   3.3
# Python Version:   3.9
#---------------------------------------------------------------------
import arcpy
import os
import sys
import multiprocessing
import datetime
import traceback
from typing import Tuple,List,Dict
import json
import chardet

#
# 次のような理由により、自前のGeoJSONからフィーチャクラスへの変換するクラスで対応する
# a)2025年1月現在JSONToFeatures を使って変換した時に PointZ のジオメトリになる
# b)フィールド型や座標系が自由に制御できない
#
# 参考
# - GistにあったGeoJSON からFeatureClass へArcPyで変換する方法を参考にしながら実装
#   https://gist.github.com/d-wasserman/070ec800584d18a22e1b5a636ca183b7
# 
class FarmlandGeojsonToFeaturesEx():
    def __init__(self):
        return
    def __del__(self):
        return
    #private
    def __write_geojson_to_records(self, jsonfile):
        #gjson_data = json.load(jsonfile, encoding='utf-8')
        #日本語が属性に入っている場合にcp932 のエラーになるので、encoding を判別して読込するように変更
        gjson_data= []
        with open(jsonfile, 'rb') as fb:
            chardic = []
            b = fb.read()
            chardic = chardet.detect(b)
            with open(jsonfile, 'r', encoding=chardic['encoding']) as fp:
                gjson_data = json.loads(fp.read())
        #農地ピンデータがない場合'title': 'Queryの結果データがありませんでした。', 'status': 404,
        if gjson_data.get("status") == 404:
            return []
        records = []
        arcpy.AddMessage("Geojson being read by row...")
        for feature in gjson_data["features"]:
            try:
                row = {}
                row["geometry"] = feature["geometry"]
                row["type"] = feature["geometry"]["type"]
                feat_dict = feature["properties"]
                for prop in feat_dict:
                    row[prop] = feat_dict[prop]
                records.append(row)
            except:
                pass
        return records

    def __get_geom_crs_code(self, record_dict):
        #geometry にCRSがある場合にCRSのコードとして取得
        keys = ["geometry", "crs", "properties", "name"]
        # Accessing the nested value using a loop
        current = record_dict
        for key in keys:
            current = current.get(key, {})
        if not current: #"Dict is Empty"
            return 0
        crs_code = int(current.split(':')[1])
        return crs_code

    #public
    def geojson_to_features(self, jsonfile, output_fc, projection=arcpy.SpatialReference(4326)):

        blResult = True
    
        try:
            path = os.path.split(output_fc)[0]
            name = os.path.split(output_fc)[1]
            
            arcpy.AddMessage(u"{0} への 変換を開始します".format(name))
            arcpy.AddMessage(u"    GeoJSON のレコード読込み中...")
            records = self.__write_geojson_to_records(jsonfile)
            arcpy.AddMessage(u"    GeoJSON の読み込み終わり")
            if len(records) == 0:
                arcpy.AddWarning(u"レコードが 0件 のため変換処理を終了します");
                return True

            gtype = records[0]["type"]
            arctype = None
            # GeoJSON Geometry : Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon
            # https://docs.ogc.org/is/17-003r2/17-003r2.html#38
            if gtype == "FeatureCollection":
                arcpy.AddWarning(u"FeatureCollections は、 point,line, polygon のいずれかに分解されます")
                arctype = "POINT" 
            elif (gtype == "LineString") or (gtype == "MultiLineString"):
                arctype = "POLYLINE" 
            elif (gtype == "MultiPolygon"):
                arctype = "POLYGON"
            else:
                arctype = str(gtype).upper() # POINT, POLYGON
            record_dict = records[0]
            #農地筆ポリゴンのGeoJSON は crs code があるようなので追加
            crs_code = self.__get_geom_crs_code(record_dict)
            if crs_code > 0:
                projection = arcpy.SpatialReference(crs_code)
            arcpy.AddMessage(u"    フィーチャクラス の新規作成...{}".format(arctype))
            arcpy.management.CreateFeatureclass(path, name, arctype, spatial_reference=projection)

            for key in record_dict:
                if key == "geometry":
                    continue
                if key == "type":
                    continue
                element = record_dict[key]
                field_type = "TEXT"
                field_length = 255
                #農地筆ポリゴンのhistory列はデフォルトの255では長さが足りないのでlengthを増やす
                if key == "history":
                    field_length = 10000
                #農地筆ポリゴンの"local_government_cd" は TEXT になってほしいので追加
                if key != "local_government_cd": 
                    try:
                        num_element = float(element)
                        #"land_type", "issue_year", "edit_year" は LONG になってほしいので追加
                        if ((key != "land_type") or (key != "issue_year") or (key != "edit_year")):
                            if isinstance(num_element, float):
                                field_type = "DOUBLE" 
                        if isinstance(element, int):
                            field_type = "LONG" 
                    except:
                        pass
                arcpy.AddField_management(in_table=output_fc, field_name=arcpy.ValidateFieldName(key, path), field_type=field_type, field_length=field_length)
            field_list = [f.name for f in arcpy.ListFields((output_fc)) if f.type not in ["OID", "Geometry"]
                              and f.name.lower() not in ["shape_area", "shape_length"]]
            fields = ["SHAPE@"] + field_list
            arcpy.AddMessage(u"    フィーチャクラス にレコードを書き込み中...")
            with arcpy.da.InsertCursor(output_fc, fields) as icursor:
                for record in records:
                    new_row = []
                    for field in fields:
                        if field == "SHAPE@":
                            try:
                                geom = arcpy.AsShape(record.setdefault("geometry", None))
                            except:
                                geom = None
                            new_row.append(geom)
                        else:
                            new_row.append(record.setdefault(str(field), None))
                    icursor.insertRow(new_row)

            arcpy.AddMessage(u"{0} への 変換完了".format(name))
        except arcpy.ExecuteError:
            arcpy.AddError(arcpy.GetMessages(2))
            blResult = False
        except Exception as e:
            arcpy.AddError(e.args[0])
            blResult = False
    
        return blResult


# 
# 補助関数の定義
# 
def __alter_field_alias(fc):
    '''
    フィールドのエイリアス名を設定する関数
    '''
    fieldsParams = [
        ["polygon_uuid", r"筆ポリゴン"],
        ["land_type", r"耕地の種類"],
        ["issue_year", r"公開年度"],
        ["edit_year", r"調製年度"],
        ["history", r"履歴"],
        ["last_polygon_uuid", r"前年筆ポリゴンID"],
        ["prev_last_polygon_uuid", r"前前年筆ポリゴンID"],
        ["local_government_cd", r"地方公共団体コード"],
        ["point_lng", r"重心点座標（経度）"],
        ["point_lat", r"重心点座標（緯度）"],
        ["old_polygon_id", r"筆ポリゴンID（旧ID 付与ルール）"]
    ]
    #"old_polygon_id"は2021年度公開の筆ポリゴンファイルのみのためfield_nameが存在している場合のみ処理
    field_names = [f.name for f in arcpy.ListFields(fc)]
    for p in fieldsParams:
        field_name = p[0]
        alias_name = p[1]
        if field_name in field_names:
            arcpy.management.AlterField(fc, field=field_name, new_field_alias=alias_name)

def __assign_domain(ws, fc):
    '''
    land_typeフィールド用に、コード値ドメインを作成して設定する関数
    '''
    domName = "land_type_CD"
    domDesc = r"耕地の種類"
    field_name = "land_type"
    #コード値ドメインの作成
    arcpy.management.CreateDomain(ws, domName, domain_description=domDesc, field_type="LONG", domain_type="CODED")
    #ドメインにコード値を追加
    domDict = {100: r"田", 200: r"畑"}
    for code in domDict:
        arcpy.management.AddCodedValueToDomain(ws, domName, code, domDict[code])
    #フィールドにドメインを適用
    arcpy.management.AssignDomainToField(fc, field_name, domName)

# 
# マルチプロセスでの処理関連
# - Python3.3 で追加された pool.starmap は複数の引数に対応しているため、ラッパー関数（ multi_run_batch_convert ）は廃止
# 
def batch_convert(in_jsonfile :str, outws :str) -> str:
    '''
    1プロセスで実行する処理:
      1) FGDBへの書込みは仕様で複数プロセスで書込みできないため
           1市区町村のGeoJSONファイルを 独自のFarmlandGeojsonToFeaturesEx クラスで1市区町村.gdb内のフィーチャクラスに変換
    
    in_jsonfile : 市区町村のGeoJSONファイルへのパス
    outws       : 出力するgdb
    '''
    if not arcpy.Exists(outws):
        outfolder = u"{0}".format(os.path.dirname(outws))
        foldername= u"{0}".format(os.path.basename(outws))
        arcpy.management.CreateFileGDB(outfolder, foldername, "CURRENT")
    filename = os.path.basename(in_jsonfile)
    in_json_file = os.path.splitext(filename)[0]
    newfc = u"c_{0}".format(in_json_file) #数値で始まるファイル名はそのまま変換できないので接頭にc_を入れる
    #独自のFarmlandGeojsonToFeaturesEx クラスで変換
    #arcpy.conversion.JSONToFeatures(in_jsonfile, os.path.join(outws, newfc))
    convGeojson = FarmlandGeojsonToFeaturesEx()
    convGeojson.geojson_to_features(in_jsonfile, os.path.join(outws, newfc))
    del convGeojson
    return u"    変換済：{0}".format(outws)

def exec_batch_convert(infolder :str, outfolder :str, cpu_cnt :int):
    '''
    マルチプロセスでの処理：
    '''
    try:
        start = datetime.datetime.now()
        arcpy.AddMessage(u"-- Strat: MP_Farmland_JsonToFeatureClass --:{0}".format(start))
        
        #a) 各プロセス用の pythonw.exe を設定
        python_path = sys.exec_prefix
        multiprocessing.set_executable(os.path.join(python_path,'pythonw.exe'))
        #multiprocessing.set_executable(os.path.join(python_path,'python.exe')) #CMDプロンプトの画面が起動するので'pythonw.exe'を使う
        
        #b) 各プロセスに渡すパラメータをリスト化
        arcpy.AddMessage(u"  Convert each GeoJSON files : multiprocessing")
        arcpy.env.workspace = infolder
        infiles = arcpy.ListFiles("*.json")
        params=[]
        for infile in infiles:
            param1 = os.path.join(infolder,infile) #市区町村のGeoJSONファイル
            filename = os.path.basename(infile)
            gdbname = u"{0}.gdb".format(os.path.splitext(filename)[0])
            param2 = os.path.join(outfolder,gdbname) # 出力する市区町村ファイルジオデータベース
            params.append((param1, param2))
        if len(infiles) < cpu_cnt: # 処理ファイル数がCPUコアより少ない場合無駄なプロセスを起動不要
            cpu_cnt = len(infiles)
        pool = multiprocessing.Pool(cpu_cnt) # cpu数分プロセス作成
        results = pool.starmap(batch_convert, params) # 割り当てプロセスで順次実行される（Python3.3で追加されたstarmapは複数の引数に対応）
        pool.close()
        pool.join()
        
        # 各プロセスでの処理結果を出力
        for r in results:
            arcpy.AddMessage(u"{0}".format(r))
        
        #c) 各プロセスで変換されたフィーチャクラスを都道府県のFGDBへマージしたものを作成（"Farmland"）
        arcpy.env.workspace = outfolder
        outwss = arcpy.ListWorkspaces("*","FileGDB")
        foldername = "{0}.gdb".format(os.path.basename(outfolder))
        fcname = "Farmland" #マージ後のフィーチャクラス名
        arcpy.AddMessage(u"  Merge to FeatureClass:{1} in FGDB:{0} ".format(foldername, fcname))
        arcpy.management.CreateFileGDB(outfolder, foldername, "CURRENT")
        prefws = os.path.join(outfolder, foldername)
        for outws in outwss:
            arcpy.env.workspace = outws
            fc = arcpy.ListFeatureClasses()[0] #農地筆は1ファイルしかないので固定
            arcpy.AddMessage(u"    merge: {0} ⇒ {1}".format(fc, fcname))
            if arcpy.Exists(os.path.join(prefws, fcname)):
                outfc = os.path.join(prefws, fcname)
                arcpy.management.Append(fc, outfc)
            else:
                arcpy.conversion.FeatureClassToFeatureClass(fc, prefws, fcname)
        
        # フィールドエイリアスを設定
        arcpy.AddMessage(u"  Alter Fields to FeatureClass:{0}".format(fcname))
        __alter_field_alias(os.path.join(prefws, fcname))
        
        # コード値ドメインを設定
        arcpy.AddMessage(u"  Assign land_type_CD domain to FeatureClass:{0}".format(fcname))
        __assign_domain(prefws, os.path.join(prefws, fcname))
        
        #d) マージが終わったので後片付け 各市区町村のFGDBを削除
        arcpy.AddMessage(u"  Delete temp FileGDBs")
        for outws in outwss:
            arcpy.AddMessage(u"    Delete FGDB:{0}".format(outws))
            arcpy.management.Delete(outws)
        
        fin = datetime.datetime.now()
        arcpy.AddMessage(u"-- Finish: MP_Farmland_JsonToFeatureClass --:{0}".format(fin))
        arcpy.AddMessage(u"     Elapsed time:{0}".format(fin-start))
    except:
        arcpy.AddError(u"Exception:{0}".format(sys.exc_info()[2]))

if __name__ == '__main__':
    '''
    コマンドプロンプトからの実行パラメータを設定の場合：
      infolder: 市区町村別の GeoJSON ファイルが入った都道府県フォルダ
      例）
        |-2024_02
            |-2024_022012.json
            |-2024_022021.json
            |-2024_022039.json
            ･････
      
      outfolder: 市区町村別の ファイルジオデータベース の作成先フォルダ
      例)
        |-2024_02_filegdb
            |-2024_022012.gdb # 市区町村別のFGDBは都道府県にマージ後削除されるようにしている（306行目～）
            |   c_2024_022012
            |-2024_022021.gdb
            |   c_2024_022021
            |-2024_022039.gdb
            |   c_2024_022039
            ･････
            |-2024_02_filegdb.gdb # 市区町村別のフィーチャクラスをマージしたフィーチャクラスを格納する都道府県のファイルジオデータベース
            |   Farmland # フィーチャクラス名
      
      cpu_cnt : マルチプロセスでの処理時に起動するプロセス数
    '''
    args = sys.argv
    if len(args) == 4:
        infolder = args[1]
        outfolder = args[2]
        cpu_cnt = int(args[3])
        exec_batch_convert(infolder, outfolder, cpu_cnt)
    else:
        print("Arguments error")
